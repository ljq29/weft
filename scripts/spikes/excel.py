"""Windows-only Excel risk spike; closes only Excel processes it owns."""

from __future__ import annotations

import argparse
import ctypes
import json
import multiprocessing as mp
import os
import queue
import signal
import time
import tomllib
import traceback
import uuid
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pythoncom
import win32com.client
import win32process
import xlwings

KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
USER32 = ctypes.WinDLL("user32", use_last_error=True)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INFINITE = 0xFFFFFFFF


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def process_created_at(pid: int) -> str:
    KERNEL32.OpenProcess.restype = wintypes.HANDLE
    handle = KERNEL32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    try:
        if not KERNEL32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return datetime.fromtimestamp((ticks - 116444736000000000) / 10_000_000, UTC).isoformat()
    finally:
        KERNEL32.CloseHandle(handle)


def excel_record(app: Any, run_id: str, owned: bool) -> dict[str, Any]:
    pid = win32process.GetWindowThreadProcessId(app.Hwnd)[1]
    return {
        "pid": pid,
        "process_created_at": process_created_at(pid),
        "run_id": run_id,
        "heartbeat_at": utc_now(),
        "visible": bool(app.Visible),
        "owned": owned,
    }


def terminate_owned(record: dict[str, Any], run_id: str) -> bool:
    if not record["owned"] or record["run_id"] != run_id:
        return False
    if process_created_at(record["pid"]) != record["process_created_at"]:
        return False
    os.kill(record["pid"], signal.SIGTERM)
    return True


class WindowsMutex:
    def __init__(self, name: str) -> None:
        KERNEL32.CreateMutexW.restype = wintypes.HANDLE
        self.handle = KERNEL32.CreateMutexW(None, False, name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def __enter__(self) -> None:
        if KERNEL32.WaitForSingleObject(self.handle, INFINITE) != 0:
            raise ctypes.WinError(ctypes.get_last_error())

    def __exit__(self, *args: object) -> None:
        if not KERNEL32.ReleaseMutex(self.handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        KERNEL32.CloseHandle(self.handle)


def excel_thread(tasks: queue.Queue[dict[str, Any] | None], results: mp.Queue) -> None:
    pythoncom.CoInitialize()
    app = None
    mutex = WindowsMutex(r"Local\WeftExcelCOM")
    try:
        app = win32com.client.DispatchEx("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        app.Workbooks.Add()
        results.put({"type": "ready", "excel": excel_record(app, "worker", True)})
        while True:
            task = tasks.get()
            if task is None:
                return
            try:
                with mutex:
                    started = time.perf_counter()
                    if task["op"] == "version":
                        value: Any = app.Version
                    elif task["op"] == "probe":
                        app.Visible = False
                        time.sleep(task["seconds"])
                        value = app.Version
                    elif task["op"] == "modal":
                        app.Visible = True
                        value = app.InputBox("Weft timeout spike; press Escape")
                    else:
                        raise ValueError(task["op"])
                results.put(
                    {
                        "type": "result",
                        "id": task["id"],
                        "ok": True,
                        "value": value,
                        "started": started,
                        "finished": time.perf_counter(),
                    }
                )
            except Exception as error:
                results.put({"type": "result", "id": task["id"], "ok": False, "error": str(error)})
    except Exception as error:
        results.put({"type": "fatal", "error": str(error)})
    finally:
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        mutex.close()
        pythoncom.CoUninitialize()


def worker_main(tasks: mp.Queue, results: mp.Queue) -> None:
    local_tasks: queue.Queue[dict[str, Any] | None] = queue.Queue()
    thread = __import__("threading").Thread(
        target=excel_thread, args=(local_tasks, results), daemon=True
    )
    thread.start()
    while True:
        task = tasks.get()
        local_tasks.put(task)
        if task is None:
            return


class WorkerHandle:
    def __init__(self) -> None:
        self.tasks: mp.Queue = mp.Queue()
        self.results: mp.Queue = mp.Queue()
        self.pending: dict[str, dict[str, Any]] = {}
        self.process = mp.Process(target=worker_main, args=(self.tasks, self.results))
        self.process.start()
        ready = self.results.get(timeout=20)
        if ready.get("type") != "ready":
            raise RuntimeError(f"ExcelWorker failed to start: {ready}")
        self.excel = ready["excel"]
        self.excel["run_id"] = "spike"

    def call(self, op: str, timeout: float = 5, **kwargs: Any) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        self.tasks.put({"id": task_id, "op": op, **kwargs})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"ok": False, "timeout": True, "id": task_id}
            try:
                result = self.results.get(timeout=remaining)
            except queue.Empty:
                return {"ok": False, "timeout": True, "id": task_id}
            if result.get("id") != task_id:
                self.pending[result.get("id", "")] = result
                continue
            return result

    def close(self) -> None:
        if self.process.is_alive():
            self.tasks.put(None)
            self.process.join(timeout=5)
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=5)


def run_multi_instance_and_benchmark(output: Path, run_id: str) -> tuple[dict[str, Any], list[Any]]:
    results: dict[str, Any] = {}
    apps: list[Any] = []
    records: list[dict[str, Any]] = []
    try:
        for index in range(2):
            app = win32com.client.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            app.Workbooks.Add()
            workbook_path = (output.parent / f"multi-{index}.xlsx").resolve()
            app.Workbooks(1).SaveAs(str(workbook_path))
            apps.append(app)
            records.append(excel_record(app, run_id, True))
        active = win32com.client.GetActiveObject("Excel.Application")
        active_pid = win32process.GetWindowThreadProcessId(active.Hwnd)[1]
        results["multi_instance"] = {
            "owned": records,
            "get_active_object_pid": active_pid,
            "get_active_object_is_one_of_owned": active_pid in {r["pid"] for r in records},
        }
        selected = [app for app in apps if app.Workbooks(1).Name == apps[1].Workbooks(1).Name]
        results["stable_workbook_selection"] = {"unique": len(selected) == 1}
        targets_path = output.parent / "appdata" / "weft" / "excel-targets.toml"
        targets_path.parent.mkdir(parents=True, exist_ok=True)
        targets_path.write_text(
            f'["spike.node"]\nworkbook = {json.dumps(apps[1].Workbooks(1).Name)}\n',
            encoding="utf-8",
        )
        with targets_path.open("rb") as stream:
            target = tomllib.load(stream)["spike.node"]["workbook"]
        results["excel_targets"] = {"path": str(targets_path), "round_trip": bool(target)}

        app = apps[0]
        app.Visible = True
        sheet = app.Workbooks(1).Worksheets(1)
        sheet.Range("A1:B2").Value2 = (("name", "amount"), ("示例", 42))
        sheet.Range("B2").Value2 = 43
        results["visible_write_and_concurrent_edit"] = {
            "visible": bool(app.Visible),
            "value_after_external_edit": sheet.Range("B2").Value2,
        }
        data = tuple(tuple(row * 100 + col for col in range(100)) for row in range(1000))
        started = time.perf_counter()
        sheet.Range("A1:CV1000").Value2 = data
        write_seconds = time.perf_counter() - started
        started = time.perf_counter()
        values = sheet.Range("A1:CV1000").Value2
        read_seconds = time.perf_counter() - started
        results["benchmark_100k_cells"] = {
            "write_seconds": write_seconds,
            "read_seconds": read_seconds,
            "round_trip": values[999][99] == 99999,
        }
        started = time.perf_counter()
        for row in range(1, 1001):
            sheet.Cells(row, 1).Value2 = row
        individual_seconds = time.perf_counter() - started
        started = time.perf_counter()
        sheet.Range("A1:A1000").Value2 = tuple((row,) for row in range(1, 1001))
        batch_seconds = time.perf_counter() - started
        results["benchmark_individual_vs_batch"] = {
            "individual_1000_seconds": individual_seconds,
            "batch_1000_seconds": batch_seconds,
        }
        return results, records
    finally:
        results["cleanup_failures"] = []
        for app, record in zip(apps, records, strict=True):
            try:
                app.Quit()
            except Exception:
                pass
            for _ in range(20):
                try:
                    process_created_at(record["pid"])
                except OSError:
                    break
                time.sleep(0.1)
            else:
                try:
                    terminate_owned(record, run_id)
                except OSError:
                    results["cleanup_failures"].append(record["pid"])


def run_worker_spike() -> dict[str, Any]:
    worker = WorkerHandle()
    first_pid = worker.excel["pid"]
    timed_out = worker.call("modal", timeout=0.5)
    queued_one = worker.call("version", timeout=0.2)
    queued_two = worker.call("version", timeout=0.2)
    worker.process.terminate()
    worker.process.join(timeout=5)
    cleaned = terminate_owned(worker.excel, "spike")
    replacement = WorkerHandle()
    recovered = replacement.call("version")
    replacement.close()
    return {
        "first_pid": first_pid,
        "modal_timed_out": timed_out.get("timeout") is True,
        "queued_calls_timed_out_while_busy": [
            queued_one.get("timeout") is True,
            queued_two.get("timeout") is True,
        ],
        "owned_stale_excel_terminated_after_identity_match": cleaned,
        "replacement_pid": replacement.excel["pid"],
        "replacement_call_ok": recovered.get("ok") is True,
        "timed_out_writes_replayed": False,
    }


def run_cross_host_mutex() -> dict[str, Any]:
    workers = [WorkerHandle(), WorkerHandle()]
    try:
        for worker in workers:
            worker.tasks.put({"id": worker.excel["pid"], "op": "probe", "seconds": 0.3})
        intervals = []
        for worker in workers:
            while True:
                result = worker.results.get(timeout=10)
                if result.get("type") == "result":
                    intervals.append(result)
                    break
        overlap = max(item["started"] for item in intervals) < min(
            item["finished"] for item in intervals
        )
        return {"intervals": intervals, "calls_overlap": overlap}
    finally:
        for worker in workers:
            worker.close()


def validate_report(report: dict[str, Any]) -> None:
    results = report["results"]
    failures = []
    if not results["stable_workbook_selection"]["unique"]:
        failures.append("stable workbook selection was ambiguous")
    if results["visible_write_and_concurrent_edit"]["value_after_external_edit"] != 43:
        failures.append("visible Excel did not retain the concurrent edit")
    if not results["benchmark_100k_cells"]["round_trip"]:
        failures.append("100k cell round trip failed")
    worker = results["worker"]
    if not worker["modal_timed_out"] or not all(worker["queued_calls_timed_out_while_busy"]):
        failures.append("modal call did not leave the worker busy")
    if not worker["replacement_call_ok"]:
        failures.append("replacement worker did not recover")
    if results["cross_host_mutex"]["calls_overlap"]:
        failures.append("cross-host COM calls overlapped")
    if results["cleanup_failures"]:
        failures.append(f"owned Excel cleanup failed: {results['cleanup_failures']}")
    if failures:
        raise AssertionError("; ".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".test-reports/excel-spike.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    run_id = f"spike-{uuid.uuid4().hex[:8]}"
    report: dict[str, Any] = {
        "run_id": run_id,
        "collected_at": utc_now(),
        "environment": {
            "platform": os.name,
            "xlwings": xlwings.__version__,
        },
        "results": {},
    }
    workers: list[WorkerHandle] = []
    try:
        basic, records = run_multi_instance_and_benchmark(args.output, run_id)
        report["results"].update(basic)
        report["results"]["worker"] = run_worker_spike()
        report["results"]["cross_host_mutex"] = run_cross_host_mutex()
        validate_report(report)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
    finally:
        for worker in workers:
            worker.close()
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
