from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import sys
import threading
import traceback
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import pyarrow as pa

from weft.excel.backend import ExcelBackend
from weft.excel.lock import ExcelGlobalLock
from weft.excel.registry import RefRegistry

_METHODS = {
    "connect",
    "workbook",
    "sheet_names",
    "read_range",
    "write_table",
    "update_cells",
    "manage_sheet",
    "save",
    "run_macro",
    "fast_mode",
    "close_app",
    "list_instances",
    "resolve",
    "probe",
}


def encode(value: Any) -> Any:
    if isinstance(value, pa.Table):
        buffer = pa.BufferOutputStream()
        with pa.ipc.new_file(buffer, value.schema) as writer:
            writer.write_table(value)
        return {
            "__weft_type__": "arrow",
            "data": base64.b64encode(buffer.getvalue().to_pybytes()).decode("ascii"),
        }
    if isinstance(value, Path):
        return {"__weft_type__": "path", "value": str(value)}
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    return value


def decode(value: Any) -> Any:
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if value.get("__weft_type__") == "arrow":
        data = base64.b64decode(value["data"])
        with pa.ipc.open_file(pa.py_buffer(data)) as reader:
            return reader.read_all()
    if value.get("__weft_type__") == "path":
        return Path(value["value"])
    return {key: decode(item) for key, item in value.items()}


@dataclass
class Job:
    request_id: str
    method: str
    args: list[Any]
    kwargs: dict[str, Any]
    run_id: str | None
    future: Future[Any]


class ExcelWorkerRuntime:
    def __init__(self, backend: ExcelBackend, output: TextIO) -> None:
        self.backend = backend
        self.output = output
        self.registry = RefRegistry()
        self.finish_modes: dict[str, str] = {}
        self.jobs: queue.Queue[Job | None] = queue.Queue()
        self.thread_id: int | None = None
        self.thread = threading.Thread(target=self._run, name="ExcelSTA", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        self.thread_id = threading.get_ident()
        if os.name == "nt":
            import pythoncom  # type: ignore[import-untyped]

            pythoncom.CoInitialize()
        try:
            while (job := self.jobs.get()) is not None:
                try:
                    with ExcelGlobalLock().acquire():
                        if job.method == "release_run":
                            result = self._release_run(job.run_id or "")
                        elif job.method == "set_run_finish":
                            self.finish_modes[job.run_id or ""] = job.args[0]
                            result = None
                        else:
                            result = self._call(job.method, job.args, job.kwargs, job.run_id)
                    job.future.set_result(result)
                except Exception as error:
                    job.future.set_exception(error)
        finally:
            if os.name == "nt":
                pythoncom.CoUninitialize()

    def _call(
        self, method: str, args: list[Any], kwargs: dict[str, Any], run_id: str | None
    ) -> Any:
        if method not in _METHODS:
            raise ValueError(f"Unsupported Excel backend method: {method}")
        if os.name == "nt" and threading.get_ident() != self.thread_id:
            raise AssertionError("Excel COM called outside the STA thread")
        resolved_args = [self._resolve(arg) for arg in args]
        resolved_kwargs = {key: self._resolve(value) for key, value in kwargs.items()}
        self.backend.active_run_id = run_id
        result = getattr(self.backend, method)(*resolved_args, **resolved_kwargs)
        return self.registry.register(result, run_id)

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, dict):
            if value.get("kind") in {"app", "workbook", "range"}:
                return self.registry.resolve(value)
            return {key: self._resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve(item) for item in value]
        return value

    def _release_run(self, run_id: str) -> dict[str, Any]:
        refs = self.registry.release_run(run_id)
        reports = []
        for ref in refs:
            if (
                isinstance(ref, dict)
                and ref.get("kind") == "app"
                and ref.get("owned")
                and not ref.get("visible")
            ):
                mode = self.finish_modes.get(run_id)
                if mode not in {"save", "discard"}:
                    raise ValueError("new_hidden requires explicit on_finish: save or discard")
                self.backend.close_app(ref, mode)
                reports.append(getattr(self.backend, "last_close_report", {}))
        self.finish_modes.pop(run_id, None)
        return {"references": refs, "close_reports": reports}

    def submit(self, job: Job) -> None:
        self.jobs.put(job)

    def close(self) -> None:
        self.jobs.put(None)
        if self.jobs.empty():
            self.thread.join(timeout=2)

    def serve(self, input_stream: TextIO) -> None:
        for line in input_stream:
            try:
                message = json.loads(line)
                request_id = message["id"]
                if message["method"] == "shutdown":
                    self._send({"id": request_id, "result": None})
                    break
                if message["method"] == "ping":
                    self._send(
                        {
                            "id": request_id,
                            "result": {
                                "pid": os.getpid(),
                                "thread_id": self.thread_id,
                                "busy": not self.jobs.empty(),
                            },
                        }
                    )
                    continue
                future: Future[Any] = Future()
                params = message.get("params", {})
                job = Job(
                    request_id=request_id,
                    method=message["method"],
                    args=[decode(arg) for arg in params.get("args", [])],
                    kwargs={key: decode(value) for key, value in params.get("kwargs", {}).items()},
                    run_id=params.get("run_id"),
                    future=future,
                )
                self.submit(job)

                def respond(done: Future[Any], request_id: str = request_id) -> None:
                    try:
                        self._send({"id": request_id, "result": encode(done.result())})
                    except Exception as error:
                        self._send(
                            {
                                "id": request_id,
                                "error": {
                                    "type": type(error).__name__,
                                    "message": str(error),
                                    "traceback": traceback.format_exc(),
                                },
                            }
                        )

                future.add_done_callback(respond)
            except Exception as error:
                self._send(
                    {
                        "id": message.get("id") if "message" in locals() else None,
                        "error": {"type": type(error).__name__, "message": str(error)},
                    }
                )
        self.close()

    def _send(self, message: dict[str, Any]) -> None:
        self.output.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.output.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["fake", "xlwings"], default="xlwings")
    args = parser.parse_args(argv)
    if args.backend == "fake":
        from weft.excel.fake import FakeExcelBackend

        backend: ExcelBackend = FakeExcelBackend()
    else:
        from weft.excel.xlwings_backend import XlwingsBackend

        backend = XlwingsBackend()
    runtime = ExcelWorkerRuntime(backend, sys.stdout)
    runtime.start()
    runtime.serve(sys.stdin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
