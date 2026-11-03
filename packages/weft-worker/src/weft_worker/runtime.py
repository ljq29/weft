from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa
from weft_sdk import Node, weft_ctx


class WorkerRuntime:
    def __init__(self) -> None:
        self.root: Path | None = None
        self.run_id = ""
        self.nodes: dict[str, Node] = {}
        self.cancelled: dict[str, threading.Event] = {}
        self.execute_lock = threading.Lock()

    def write(self, value: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def init(self, params: dict[str, Any]) -> dict[str, Any]:
        self.root = Path(params["root"])
        self.run_id = params["run_id"]
        from weft_worker.builtin import BUILTIN_NODES

        self.nodes = {node.type: node for node in (item() for item in BUILTIN_NODES)}
        for path in sorted((self.root / "nodes").glob("*.py")):
            spec = importlib.util.spec_from_file_location(f"weft_user_{path.stem}", path)
            if spec is None or spec.loader is None:
                raise ImportError(path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for _, value in inspect.getmembers(module, inspect.isclass):
                if (
                    value is not Node
                    and issubclass(value, Node)
                    and value.__dict__.get("__weft_node__", False)
                ):
                    node = value()
                    self.nodes[node.type] = node
        return {"initialized": True}

    def execute(self, request_id: Any, params: dict[str, Any]) -> None:
        def work() -> None:
            with self.execute_lock:
                result = self.execute_now(params)
                self.write({"jsonrpc": "2.0", "id": request_id, "result": result})

        threading.Thread(target=work, daemon=True).start()

    def execute_now(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.root is None:
            raise RuntimeError("Worker is not initialized")
        node_exec_id = params["node_exec_id"]
        cancel = threading.Event()
        self.cancelled[node_exec_id] = cancel
        try:
            inputs = {
                port: self.read_value(reference)
                for port, reference in params.get("inputs", {}).items()
            }
            node = self.nodes[params["node_type"]]
            with weft_ctx.activate(
                root=self.root,
                run_id=self.run_id,
                variables=params.get("ctx", {}).get("vars", {}),
                log=lambda level, message: self.write(
                    {
                        "jsonrpc": "2.0",
                        "method": "log",
                        "params": {
                            "node_exec_id": node_exec_id,
                            "level": level,
                            "message": message,
                        },
                    }
                ),
                progress=lambda fraction, message: self.write(
                    {
                        "jsonrpc": "2.0",
                        "method": "progress",
                        "params": {
                            "node_exec_id": node_exec_id,
                            "fraction": fraction,
                            "message": message,
                        },
                    }
                ),
                cancelled=cancel.is_set,
            ):
                outputs = node.execute(weft_ctx, inputs, params["params"])
            activated = outputs.pop("activated_ports", None)
            serialized = {
                port: self.write_value(node_exec_id, port, value) for port, value in outputs.items()
            }
            result: dict[str, Any] = {"outputs": serialized}
            if activated is not None:
                result["activated_ports"] = activated
            return result
        except Exception as error:
            return {
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                    "traceback": traceback.format_exc(),
                }
            }
        finally:
            self.cancelled.pop(node_exec_id, None)

    def cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        event = self.cancelled.get(params["node_exec_id"])
        if event is not None:
            event.set()
        return {"cancelled": event is not None}

    def read_value(self, reference: dict[str, Any]) -> Any:
        if self.root is None:
            raise RuntimeError("Worker is not initialized")
        if reference["kind"] == "none":
            return None
        if reference.get("path") is None:
            return reference.get("inline")
        path = Path(reference["path"])
        if not path.is_absolute():
            path = self.root / path
        if reference["kind"] == "json":
            return json.loads(path.read_text(encoding="utf-8"))
        with pa.memory_map(str(path)) as source:
            return pl.from_arrow(pa.ipc.open_file(source).read_all())

    def write_value(self, node_exec_id: str, port: str, value: Any) -> dict[str, Any]:
        if self.root is None:
            raise RuntimeError("Worker is not initialized")
        if isinstance(value, pl.DataFrame):
            directory = self.root / ".runs" / self.run_id / "ipc" / node_exec_id
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{port}.arrow"
            with path.open("wb") as stream:
                with pa.ipc.new_file(stream, value.to_arrow().schema) as writer:
                    writer.write_table(value.to_arrow())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return {
                "kind": "table",
                "path": str(path),
                "hash": f"sha256:{digest}",
                "rows": value.height,
                "cols": value.width,
            }
        data = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
        if len(data) <= 256 * 1024:
            return {"kind": "json", "inline": value, "hash": digest}
        directory = self.root / ".runs" / self.run_id / "ipc" / node_exec_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{port}.json"
        path.write_bytes(data)
        return {"kind": "json", "path": str(path), "hash": digest}


def serve() -> int:
    runtime = WorkerRuntime()
    for line in sys.stdin:
        request = json.loads(line)
        request_id = request.get("id")
        method = request["method"]
        params = request.get("params", {})
        try:
            if method == "execute":
                runtime.execute(request_id, params)
            else:
                if method == "init":
                    result = runtime.init(params)
                elif method == "cancel":
                    result = runtime.cancel(params)
                elif method == "shutdown":
                    result = {"stopped": True}
                else:
                    raise ValueError(f"Unknown method: {method}")
                runtime.write({"jsonrpc": "2.0", "id": request_id, "result": result})
                if method == "shutdown":
                    return 0
        except Exception as error:
            runtime.write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "error": {
                            "type": type(error).__name__,
                            "message": str(error),
                            "traceback": traceback.format_exc(),
                        }
                    },
                }
            )
    return 0
