from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from weft.worker.environment import WorkflowEnvironment


class WorkerCrashedError(RuntimeError):
    pass


class WorkerProcess:
    def __init__(
        self,
        environment: WorkflowEnvironment,
        run_id: str,
        env: dict[str, str],
        on_log: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.environment = environment
        self.run_id = run_id
        self.on_log = on_log
        self.responses: dict[Any, dict[str, Any]] = {}
        self.condition = threading.Condition()
        self.execute_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.active_tasks: set[str] = set()
        log_dir = environment.root / ".runs" / run_id
        log_dir.mkdir(parents=True, exist_ok=True)
        self.stderr = (log_dir / f"worker-{uuid.uuid4().hex[:6]}.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(environment.python), "-m", "weft_worker.cli", "serve"],
            cwd=environment.root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.reader = threading.Thread(target=self.read_loop, daemon=True)
        self.reader.start()
        self.request(
            "init",
            {"root": str(environment.root), "run_id": run_id, "node_types_manifest": {}},
        )

    def read_loop(self) -> None:
        if self.process.stdout is None:
            return
        for line in self.process.stdout:
            message = json.loads(line)
            if message.get("method") == "log" and self.on_log is not None:
                params = message.get("params", {})
                self.on_log(
                    str(params.get("node_exec_id", "")),
                    str(params.get("level", "INFO")),
                    str(params.get("message", "")),
                )
            if "id" in message:
                with self.condition:
                    self.responses[message["id"]] = message
                    self.condition.notify_all()

    def request(self, method: str, params: dict[str, Any], timeout: float = 300) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        with self.write_lock:
            if self.process.poll() is not None or self.process.stdin is None:
                raise WorkerCrashedError(f"Worker exited with {self.process.returncode}")
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        with self.condition:
            while request_id not in self.responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Worker request {method} timed out")
                if self.process.poll() is not None:
                    raise WorkerCrashedError(f"Worker exited with {self.process.returncode}")
                self.condition.wait(timeout=min(remaining, 0.1))
            result = self.responses.pop(request_id)["result"]
            if not isinstance(result, dict):
                raise TypeError("Worker result must be an object")
            return result

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        node_exec_id = params["node_exec_id"]
        with self.execute_lock:
            self.active_tasks.add(node_exec_id)
            try:
                return self.request("execute", params)
            finally:
                self.active_tasks.discard(node_exec_id)

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.request("shutdown", {}, timeout=2)
                self.process.wait(timeout=2)
            except (TimeoutError, WorkerCrashedError):
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
        self.stderr.close()


class WorkerPool:
    def __init__(self, environment: WorkflowEnvironment, run_id: str, size: int = 4) -> None:
        self.environment = environment
        self.run_id = run_id
        self.size = size
        self.workers: list[WorkerProcess] = []
        self.worker_env = dict(os.environ)
        self.worker_env.pop("PYTHONPATH", None)
        self.worker_env["PYTHONNOUSERSITE"] = "1"
        self.worker_env["PYTHONIOENCODING"] = "utf-8"
        self._lock = threading.Lock()
        self._next = 0
        self.on_log: Callable[[str, str, str], None] | None = None

    def start(self) -> None:
        if self.workers:
            return
        self.workers = [
            WorkerProcess(self.environment, self.run_id, self.worker_env, self.on_log)
            for _ in range(self.size)
        ]

    async def execute(
        self,
        node_exec_id: str,
        node_type: str,
        params: dict[str, Any],
        inputs: dict[str, Any],
        vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self.execute_sync, node_exec_id, node_type, params, inputs, vars or {}
        )

    def execute_sync(
        self,
        node_exec_id: str,
        node_type: str,
        params: dict[str, Any],
        inputs: dict[str, Any],
        vars: dict[str, Any],
    ) -> dict[str, Any]:
        self.start()
        with self._lock:
            worker = self.workers[self._next % len(self.workers)]
            self._next += 1
        return worker.execute(
            {
                "node_exec_id": node_exec_id,
                "node_type": node_type,
                "params": params,
                "inputs": inputs,
                "ctx": {"vars": vars},
            }
        )

    async def cancel(self, node_exec_id: str) -> None:
        await asyncio.to_thread(self.cancel_sync, node_exec_id)

    def cancel_sync(self, node_exec_id: str) -> None:
        for worker in self.workers:
            worker.request("cancel", {"node_exec_id": node_exec_id})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if all(node_exec_id not in worker.active_tasks for worker in self.workers):
                return
            time.sleep(0.05)
        for worker in self.workers:
            if node_exec_id in worker.active_tasks and worker.process.poll() is None:
                worker.process.terminate()

    @property
    def process_ids(self) -> list[int]:
        return [worker.process.pid for worker in self.workers]

    def close(self) -> None:
        for worker in self.workers:
            worker.close()
        self.workers = []
