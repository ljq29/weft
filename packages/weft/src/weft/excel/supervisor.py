from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from weft.excel.worker import decode, encode


class ExcelWorkerError(RuntimeError):
    def __init__(self, message: str, code: str = "EXCEL_WORKER_ERROR") -> None:
        super().__init__(message)
        self.code = code


class ExcelWorkerRestartedError(ExcelWorkerError):
    def __init__(self) -> None:
        super().__init__(
            "ExcelWorker restarted; the queued operation was not executed or replayed",
            "EXCEL_WORKER_RESTARTED",
        )


class ExcelWorkerProcess:
    def __init__(self, backend: str) -> None:
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        self.process = subprocess.Popen(
            [sys.executable, "-m", "weft.excel.worker", "--backend", backend],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=environment,
        )
        self.responses: dict[str, dict[str, Any]] = {}
        self.pending: set[str] = set()
        self.inflight: set[str] = set()
        self.restarted: set[str] = set()
        self.condition = threading.Condition()
        self.write_lock = threading.Lock()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        if self.process.stdout is None:
            return
        for line in self.process.stdout:
            message = json.loads(line)
            request_id = message.get("id")
            with self.condition:
                self.responses[request_id] = message
                self.pending.discard(request_id)
                self.inflight.discard(request_id)
                self.condition.notify_all()
        with self.condition:
            self.condition.notify_all()

    def request(
        self,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any],
        run_id: str | None,
        timeout: float,
    ) -> Any:
        request_id = uuid.uuid4().hex
        message = {
            "id": request_id,
            "method": method,
            "params": {"args": encode(args), "kwargs": encode(kwargs), "run_id": run_id},
        }
        with self.condition:
            self.pending.add(request_id)
            self.inflight.add(request_id)
        try:
            with self.write_lock:
                if self.process.poll() is not None or self.process.stdin is None:
                    raise ExcelWorkerError("ExcelWorker is not running", "EXCEL_WORKER_CRASHED")
                self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                self.process.stdin.flush()
            return self.wait(request_id, timeout)
        except Exception:
            with self.condition:
                self.pending.discard(request_id)
                self.responses.pop(request_id, None)
            raise

    def wait(self, request_id: str, timeout: float) -> Any:
        deadline = time.monotonic() + timeout
        with self.condition:
            while request_id not in self.responses:
                if request_id in self.restarted:
                    self.restarted.discard(request_id)
                    self.pending.discard(request_id)
                    raise ExcelWorkerRestartedError
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Excel call timed out; the worker is still busy")
                if self.process.poll() is not None:
                    raise ExcelWorkerError("ExcelWorker exited", "EXCEL_WORKER_CRASHED")
                self.condition.wait(min(remaining, 0.1))
            message = self.responses.pop(request_id)
        if "error" in message:
            error = message["error"]
            raise ExcelWorkerError(error["message"], error["type"])
        return decode(message.get("result"))

    def fail_pending(self) -> None:
        with self.condition:
            self.restarted.update(self.pending)
            self.pending.clear()
            self.inflight.clear()
            self.condition.notify_all()

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()


class ExcelWorkerSupervisor:
    def __init__(
        self,
        backend: str = "xlwings",
        call_timeout: float = 60,
        restart_after_timeouts: int = 3,
    ) -> None:
        self.backend = backend
        self.call_timeout = call_timeout
        self.restart_after_timeouts = restart_after_timeouts
        self._process: ExcelWorkerProcess | None = None
        self._state = threading.Lock()
        self._timeouts = 0
        self._run_ids: set[str] = set()

    def start(self) -> None:
        self._ensure()

    def _ensure(self) -> ExcelWorkerProcess:
        with self._state:
            if self._process is not None and self._process.process.poll() is None:
                return self._process
            if self._process is not None:
                self._restart_locked()
            self._process = ExcelWorkerProcess(self.backend)
            self._timeouts = 0
            process = self._process
        process.request("ping", [], {}, None, 5)
        return process

    async def submit(
        self,
        fn: str | Callable[..., Any],
        *args: Any,
        timeout: float | None = None,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        method = fn if isinstance(fn, str) else fn.__name__
        return await asyncio.to_thread(
            self._submit, method, list(args), kwargs, timeout or self.call_timeout, run_id
        )

    def _submit(
        self,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any],
        timeout: float,
        run_id: str | None,
    ) -> Any:
        process = self._ensure()
        if run_id is not None:
            self._run_ids.add(run_id)
        from weft.operations import log_excel_call

        log_excel_call(method, run_id)
        try:
            result = process.request(method, args, kwargs, run_id, timeout)
        except TimeoutError:
            with self._state:
                self._timeouts += 1
                if self._timeouts >= self.restart_after_timeouts and self._process is process:
                    self._restart_locked()
            raise
        with self._state:
            self._timeouts = 0
        return result

    def check_health(self) -> bool:
        process = self._ensure()
        try:
            process.request("ping", [], {}, None, 1)
            return True
        except (TimeoutError, ExcelWorkerError):
            with self._state:
                if self._process is process:
                    self._restart_locked()
            return False

    def _restart_locked(self) -> None:
        process = self._process
        self._process = None
        self._timeouts = 0
        if process is not None:
            process.fail_pending()
            process.close()
        self._cleanup_owned()

    def _cleanup_owned(self) -> None:
        if self.backend != "xlwings" or os.name != "nt":
            return
        from weft.excel.xlwings_backend import OwnedProcessRegistry

        registry = OwnedProcessRegistry()
        for run_id in self._run_ids:
            registry.cleanup_run(run_id)

    @property
    def busy(self) -> bool:
        return bool(self._process and self._process.inflight)

    @property
    def pending_count(self) -> int:
        return len(self._process.pending) if self._process is not None else 0

    async def release_run(self, run_id: str, on_finish: str | None = None) -> dict[str, Any]:
        if on_finish is not None and on_finish not in {"save", "discard"}:
            raise ValueError("on_finish must be save or discard")
        if self._process is None:
            self._run_ids.discard(run_id)
            return {"references": [], "close_reports": []}
        if on_finish is not None:
            await self.submit("set_run_finish", on_finish, run_id=run_id)
        result = await self.submit("release_run", run_id=run_id)
        if not isinstance(result, dict):
            raise TypeError("release_run must return an object")
        self._run_ids.discard(run_id)
        return result

    def close(self) -> None:
        with self._state:
            process = self._process
            self._process = None
        if process is not None:
            try:
                process.request("shutdown", [], {}, None, 1)
                process.process.wait(timeout=2)
            except (ExcelWorkerError, TimeoutError, subprocess.TimeoutExpired):
                pass
            finally:
                process.close()
        self._cleanup_owned()
