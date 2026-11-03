from __future__ import annotations

import ctypes
import json
import os
import re
import signal
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from ctypes import wintypes
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

import pyarrow as pa
import pythoncom  # type: ignore[import-untyped]
import win32com.client  # type: ignore[import-untyped]
import win32process  # type: ignore[import-untyped]

T = TypeVar("T")
_BUSY_HRESULTS = {-2147418111, -2146777998}
_FORMATS = {"xlsx": 51, "xlsm": 52, "csv": 6}


class ExcelBusyError(RuntimeError):
    pass


def excel_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return (value - datetime(1899, 12, 30)).total_seconds() / 86400
    return value


def _hresult(error: BaseException) -> int | None:
    value = getattr(error, "hresult", None)
    if value is not None:
        return int(value)
    info = getattr(error, "excepinfo", None)
    return int(info[5]) if info and info[5] is not None else None


def process_created_at(pid: int) -> str:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    try:
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel32.CloseHandle(handle)
    ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    return datetime.fromtimestamp((ticks - 116444736000000000) / 10_000_000, UTC).isoformat()


def process_alive(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    exit_code = wintypes.DWORD()
    try:
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return exit_code.value == 259
    finally:
        kernel32.CloseHandle(handle)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class OwnedProcessRegistry:
    def __init__(self, path: Path | None = None) -> None:
        state = os.environ.get("WEFT_EXCEL_STATE_DIR")
        self.path = path or Path(state or Path.home() / ".weft") / "owned-excel.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        temporary = self.path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def register(self, record: dict[str, Any]) -> None:
        records = self._read()
        records[str(record["pid"])] = record
        self._write(records)

    def heartbeat(self, pid: int) -> None:
        records = self._read()
        if str(pid) in records:
            records[str(pid)]["heartbeat_at"] = utc_now()
            self._write(records)

    def remove(self, pid: int) -> None:
        records = self._read()
        records.pop(str(pid), None)
        self._write(records)

    def cleanup_run(self, run_id: str) -> list[int]:
        cleaned: list[int] = []
        records = self._read()
        for record in records.values():
            if not record.get("owned") or record.get("visible") or record.get("run_id") != run_id:
                continue
            try:
                if process_created_at(record["pid"]) != record["process_created_at"]:
                    continue
                os.kill(record["pid"], signal.SIGTERM)
            except OSError:
                pass
            cleaned.append(record["pid"])
            self.remove(record["pid"])
        return cleaned

    def cleanup(self) -> list[int]:
        cleaned: list[int] = []
        records = self._read()
        for record in records.values():
            if not record.get("owned") or record.get("visible") or not record.get("run_id"):
                continue
            try:
                if process_created_at(record["pid"]) != record["process_created_at"]:
                    continue
                heartbeat = datetime.fromisoformat(record["heartbeat_at"])
                if (datetime.now(UTC) - heartbeat).total_seconds() < 30:
                    continue
                os.kill(record["pid"], signal.SIGTERM)
                cleaned.append(record["pid"])
            except (OSError, KeyError, ValueError):
                continue
        return cleaned


class XlwingsBackend:
    def __init__(self) -> None:
        self.apps: dict[int, Any] = {}
        self.workbooks: dict[str, Any] = {}
        self.active_run_id: str | None = None
        self.owned = OwnedProcessRegistry()
        self.last_close_report: dict[str, Any] = {}

    def _retry(self, operation: Callable[[], T]) -> T:
        for attempt in range(3):
            try:
                return operation()
            except Exception as error:
                if _hresult(error) not in _BUSY_HRESULTS or attempt == 2:
                    if _hresult(error) in _BUSY_HRESULTS:
                        raise ExcelBusyError("Excel is busy (modal dialog open?)") from error
                    raise
                time.sleep(1)
        raise AssertionError("unreachable")

    def _app_ref(self, app: Any, owned: bool) -> dict[str, Any]:
        pid = win32process.GetWindowThreadProcessId(app.Hwnd)[1]
        self.apps[pid] = app
        record = {
            "pid": pid,
            "process_created_at": process_created_at(pid),
            "run_id": self.active_run_id,
            "heartbeat_at": utc_now(),
            "visible": bool(app.Visible),
            "owned": owned,
        }
        if owned:
            self.owned.register(record)
        return {
            "kind": "app",
            "pid": pid,
            "visible": record["visible"],
            "owned": owned,
            "process_created_at": record["process_created_at"],
            "workbooks": [book.Name for book in app.Workbooks],
        }

    def _instances(self) -> list[Any]:
        found: dict[int, Any] = {}
        try:
            rot = pythoncom.GetRunningObjectTable()
            context = pythoncom.CreateBindCtx()
            for moniker in rot.EnumRunning():
                try:
                    dispatch = moniker.BindToObject(context, None, pythoncom.IID_IDispatch)
                    candidate = win32com.client.Dispatch(dispatch)
                    app = candidate.Application if hasattr(candidate, "Parent") else candidate
                    if not app.Visible:
                        continue
                    pid = win32process.GetWindowThreadProcessId(app.Hwnd)[1]
                    found[pid] = app
                except Exception:
                    continue
        except Exception:
            pass
        if not found:
            try:
                app = win32com.client.GetActiveObject("Excel.Application")
                pid = win32process.GetWindowThreadProcessId(app.Hwnd)[1]
                found[pid] = app
            except Exception:
                pass
        return list(found.values())

    def list_instances(self) -> list[dict[str, Any]]:
        return [
            {
                "pid": win32process.GetWindowThreadProcessId(app.Hwnd)[1],
                "title": app.Caption,
                "visible": bool(app.Visible),
                "workbooks": [book.Name for book in app.Workbooks],
                "paths": [book.FullName for book in app.Workbooks if book.Path],
            }
            for app in self._instances()
        ]

    def connect(self, mode: str, target: dict[str, Any] | None = None) -> dict[str, Any]:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Excel.Application"):
                pass
        except OSError as error:
            raise RuntimeError("Excel is not installed or not registered") from error
        if mode == "attach_visible":
            candidates = self._instances()
            if target:
                matched = []
                for app in candidates:
                    pid = win32process.GetWindowThreadProcessId(app.Hwnd)[1]
                    books = list(app.Workbooks)
                    if target.get("pid") is not None and target["pid"] != pid:
                        continue
                    if target.get("workbook") and not any(
                        book.Name == target["workbook"] for book in books
                    ):
                        continue
                    if target.get("path") and not any(
                        book.FullName.lower() == target["path"].lower() for book in books
                    ):
                        continue
                    matched.append(app)
                candidates = matched
            if not candidates:
                if target:
                    raise ValueError("Saved Excel target cannot be resolved")
                app = win32com.client.DispatchEx("Excel.Application")
                app.Visible = True
                return self._retry(lambda: self._app_ref(app, True))
            if len(candidates) != 1:
                raise ValueError("Saved Excel target is ambiguous; choose an instance explicitly")
            return self._retry(lambda: self._app_ref(candidates[0], False))
        app = win32com.client.DispatchEx("Excel.Application")
        app.Visible = mode == "new_visible"
        app.DisplayAlerts = False
        return self._retry(lambda: self._app_ref(app, True))

    def _app(self, ref: dict[str, Any]) -> Any:
        app = self.apps.get(ref["pid"])
        if app is None:
            matches = [
                app
                for app in self._instances()
                if win32process.GetWindowThreadProcessId(app.Hwnd)[1] == ref["pid"]
            ]
            if len(matches) != 1:
                raise ValueError("Excel application cannot be resolved")
            app = matches[0]
            self.apps[ref["pid"]] = app
        if ref.get("owned"):
            self.owned.heartbeat(ref["pid"])
        return app

    def _workbook_ref(self, workbook: Any) -> dict[str, Any]:
        saved = bool(workbook.Path)
        path = workbook.FullName if saved else None
        pid = win32process.GetWindowThreadProcessId(workbook.Application.Hwnd)[1]
        identifier = f"{pid}:{workbook.Name}"
        self.workbooks[identifier] = workbook
        return {
            "kind": "workbook",
            "id": identifier,
            "app_pid": pid,
            "name": workbook.Name,
            "path": path,
            "saved": saved,
        }

    def workbook(
        self, app: dict[str, Any], mode: str, name_or_path: str | None = None
    ) -> dict[str, Any]:
        application = self._app(app)
        books = list(application.Workbooks)
        if mode == "open_existing":
            for book in books:
                if book.Name == name_or_path:
                    return self._workbook_ref(book)
            raise ValueError(
                f"工作簿未打开：{name_or_path}；已打开：{[book.Name for book in books]}"
            )
        if mode == "open_file":
            path = Path(name_or_path or "").resolve()
            for book in books:
                try:
                    if Path(book.FullName).resolve() == path:
                        return self._workbook_ref(book)
                except OSError:
                    continue
            if not path.is_file():
                raise FileNotFoundError(str(path))
            return self._retry(lambda: self._workbook_ref(application.Workbooks.Open(str(path))))
        if mode == "new":
            return self._retry(lambda: self._workbook_ref(application.Workbooks.Add()))
        raise ValueError(f"Unknown workbook mode: {mode}")

    def _workbook(self, ref: dict[str, Any]) -> Any:
        if ref.get("id") in self.workbooks:
            return self.workbooks[ref["id"]]
        app = self._app({"pid": ref["app_pid"], "owned": False})
        for book in app.Workbooks:
            if book.Name == ref["name"]:
                self.workbooks[ref.get("id", f"{ref['app_pid']}:{ref['name']}")] = book
                return book
        raise ValueError(f"工作簿无法解析：{ref['name']}")

    def sheet_names(self, workbook: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"name": sheet.Name, "index": sheet.Index, "visible": bool(sheet.Visible)}
            for sheet in self._workbook(workbook).Worksheets
        ]

    def _sheet(self, workbook: dict[str, Any], name: str) -> Any:
        book = self._workbook(workbook)
        sheets = list(book.Worksheets)
        for sheet in sheets:
            if sheet.Name == name:
                return sheet
        raise ValueError(f"工作表不存在：{name}；可用：{[sheet.Name for sheet in sheets]}")

    def _range(self, book: Any, sheet: Any, spec: str) -> Any:
        if not spec:
            return sheet.UsedRange
        if ":" in spec or re.fullmatch(r"\$?[A-Z]+\$?\d+", spec, re.IGNORECASE):
            return sheet.Range(spec)
        try:
            return sheet.ListObjects(spec).Range
        except Exception:
            try:
                return sheet.Names(spec).RefersToRange
            except Exception:
                return book.Names(spec).RefersToRange

    def read_range(
        self,
        workbook: dict[str, Any],
        sheet: str,
        range_spec: str,
        header: bool,
        dtype_hints: dict[str, Any],
    ) -> pa.Table:
        book = self._workbook(workbook)
        target_sheet = self._sheet(workbook, sheet)
        area = self._range(book, target_sheet, range_spec)
        values = self._retry(lambda: area.Value2)
        if values is None:
            values = ()
        elif not isinstance(values, tuple):
            values = ((values,),)
        elif values and not isinstance(values[0], tuple):
            values = (values,)
        number_format = area.NumberFormat
        is_date = (
            isinstance(number_format, str)
            and "y" in number_format.lower()
            and "d" in number_format.lower()
        )
        epoch = datetime(1899, 12, 30)
        rows = [
            [
                epoch + timedelta(days=float(value))
                if is_date and isinstance(value, (int, float))
                else value
                for value in row
            ]
            for row in values
        ]
        if header and rows:
            names = [str(value or f"Column_{index}") for index, value in enumerate(rows.pop(0))]
        else:
            names = [f"Column_{index + 1}" for index in range(len(rows[0]) if rows else 0)]
        columns: dict[str, list[Any]] = {
            name: [row[index] if index < len(row) else None for row in rows]
            for index, name in enumerate(names)
        }
        arrays: dict[str, pa.Array] = {}
        for name, values_list in columns.items():
            nonnull = [value for value in values_list if value is not None]
            hint = dtype_hints.get(name)
            if hint:
                arrays[name] = pa.array(values_list, type=pa.type_for_alias(hint))
            elif nonnull and all(
                isinstance(value, (int, float)) and not isinstance(value, bool) for value in nonnull
            ):
                integral = all(
                    isinstance(value, int) or float(value).is_integer() for value in nonnull
                )
                arrays[name] = pa.array(
                    [int(value) if value is not None else None for value in values_list]
                    if integral
                    else [float(value) if value is not None else None for value in values_list]
                )
            elif nonnull and not all(isinstance(value, type(nonnull[0])) for value in nonnull):
                arrays[name] = pa.array(
                    [str(value) if value is not None else None for value in values_list]
                )
            else:
                arrays[name] = pa.array(values_list)
        return pa.table(arrays)

    def write_table(
        self,
        workbook: dict[str, Any],
        sheet: str,
        start: str,
        table: pa.Table,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        book = self._workbook(workbook)
        fast = options.get("fast_mode", not bool(book.Application.Visible))
        if not fast:
            return self._write_table(workbook, sheet, start, table, mode, options)
        pid = win32process.GetWindowThreadProcessId(book.Application.Hwnd)[1]
        with self.fast_mode({"pid": pid}):
            return self._write_table(workbook, sheet, start, table, mode, options)

    def _write_table(
        self,
        workbook: dict[str, Any],
        sheet: str,
        start: str,
        table: pa.Table,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        book = self._workbook(workbook)
        try:
            target_sheet = self._sheet(workbook, sheet)
        except ValueError:
            target_sheet = book.Worksheets.Add()
            target_sheet.Name = sheet
        column = target_sheet.Range(start).Column
        start_row = target_sheet.Range(start).Row
        if mode == "append":
            if target_sheet.Cells(1, column).Value2 is None:
                start_row = 1
            else:
                start_row = target_sheet.Cells(target_sheet.Rows.Count, column).End(-4162).Row + 1
        rows = [list(row.values()) for row in table.to_pylist()]
        values = (
            [table.column_names, *rows]
            if options.get("header", True) and mode != "append"
            else rows
        )
        if mode == "overwrite" and options.get("clear_below", True):
            last_row = max(
                start_row, target_sheet.UsedRange.Row + target_sheet.UsedRange.Rows.Count - 1
            )
            last_column = column + max(0, table.num_columns - 1)
            target_sheet.Range(
                target_sheet.Cells(start_row, column), target_sheet.Cells(last_row, last_column)
            ).ClearContents()
        allow_formula = options.get("allow_formula", False)
        safe_values = [
            [
                "'" + value
                if isinstance(value, str) and value.startswith("=") and not allow_formula
                else excel_value(value)
                for value in row
            ]
            for row in values
        ]
        end_row = start_row + max(1, len(values)) - 1
        end_column = column + max(1, table.num_columns) - 1
        area = target_sheet.Range(
            target_sheet.Cells(start_row, column), target_sheet.Cells(end_row, end_column)
        )
        if safe_values:

            def write_values() -> None:
                if allow_formula:
                    area.Formula = tuple(map(tuple, safe_values))
                else:
                    area.Value2 = tuple(map(tuple, safe_values))

            self._retry(write_values)
            if options.get("autofit"):
                area.Columns.AutoFit()
        address = area.Address
        return {
            "kind": "range",
            "workbook": workbook,
            "sheet": sheet,
            "address": address,
            "rows": len(values),
            "cols": table.num_columns,
        }

    def update_cells(
        self, workbook: dict[str, Any], sheet: str, cells: list[dict[str, Any]], allow_formula: bool
    ) -> None:
        target_sheet = self._sheet(workbook, sheet)
        for item in cells:
            if not re.fullmatch(r"\$?[A-Z]+\$?[1-9]\d*", item["address"], re.IGNORECASE):
                raise ValueError(f"Invalid cell address: {item['address']}")
            target_sheet.Range(item["address"])
        for item in cells:
            value = excel_value(item["value"])
            if isinstance(value, str) and value.startswith("=") and not allow_formula:
                value = "'" + value
            target = target_sheet.Range(item["address"])

            def operation(target: Any = target, value: Any = value) -> None:
                setattr(target, "Formula" if allow_formula else "Value", value)

            self._retry(operation)

    def manage_sheet(
        self, workbook: dict[str, Any], action: str, name: str, new_name: str | None = None
    ) -> None:
        book = self._workbook(workbook)
        if action == "create":
            book.Worksheets.Add().Name = name
            return
        sheet = self._sheet(workbook, name)
        if action == "delete":
            if len(book.Worksheets) == 1:
                raise ValueError("不能删除最后一张工作表")
            previous = book.Application.DisplayAlerts
            try:
                book.Application.DisplayAlerts = False
                sheet.Delete()
            finally:
                book.Application.DisplayAlerts = previous
        elif action == "rename":
            sheet.Name = new_name or name
        elif action == "clear":
            sheet.Cells.ClearContents()
        else:
            raise ValueError(f"Unknown sheet action: {action}")

    def save(
        self,
        workbook: dict[str, Any],
        mode: str,
        path: Path | None = None,
        fmt: str | None = None,
        overwrite: bool = False,
    ) -> Path | None:
        book = self._workbook(workbook)
        if mode == "save":
            if not workbook.get("path"):
                raise ValueError("未保存工作簿请使用 save_as")
            book.Save()
            self._workbook_ref(book)
            return Path(book.FullName)
        if mode != "save_as" or path is None:
            raise ValueError("save_as requires a path")
        target = path.resolve()
        if target.exists() and not overwrite:
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        previous = book.Application.DisplayAlerts
        try:
            book.Application.DisplayAlerts = False
            book.SaveAs(str(target), FileFormat=_FORMATS.get(fmt or target.suffix.lstrip("."), 51))
        finally:
            book.Application.DisplayAlerts = previous
        self._workbook_ref(book)
        return target

    def run_macro(self, workbook: dict[str, Any], macro: str, args: list[Any]) -> Any:
        return self._workbook(workbook).Application.Run(macro, *args)

    @contextmanager
    def fast_mode(self, app: dict[str, Any]) -> Iterator[None]:
        application = self._app(app)
        previous = (application.ScreenUpdating, application.Calculation, application.EnableEvents)
        application.ScreenUpdating = False
        application.Calculation = -4135
        application.EnableEvents = False
        try:
            yield
        finally:
            application.ScreenUpdating, application.Calculation, application.EnableEvents = previous

    def close_app(self, app: dict[str, Any], on_finish: str) -> None:
        if on_finish not in {"save", "discard"}:
            raise ValueError("on_finish must be explicitly save or discard")
        if not app.get("owned"):
            return
        application = self._app(app)
        record = self.owned._read().get(str(app["pid"]), {})
        unsaved = [book.Name for book in application.Workbooks if not book.Saved and not book.Path]
        self.last_close_report = {"unsaved": unsaved}
        if on_finish == "save":
            for book in application.Workbooks:
                if not book.Saved and book.Path:
                    book.Save()
        application.DisplayAlerts = False
        application.Quit()
        for _ in range(20):
            if not process_alive(app["pid"]):
                break
            time.sleep(0.1)
        else:
            if record.get("run_id"):
                self.owned.cleanup_run(record["run_id"])
        self.owned.remove(app["pid"])
        self.apps.pop(app["pid"], None)
        for identifier in [key for key in self.workbooks if key.startswith(f"{app['pid']}:")]:
            self.workbooks.pop(identifier, None)

    def probe(
        self, app: dict[str, Any] | None = None, delay: float = 0, modal: bool = False
    ) -> dict[str, Any]:
        if modal:
            if app is None:
                raise ValueError("A modal probe requires an owned app")
            application = self._app(app)
            application.Visible = True
            application.InputBox("Weft recovery test; worker will be terminated")
        time.sleep(delay)
        return {"pid": os.getpid(), "modal": modal}

    def resolve(self, ref: dict[str, Any]) -> bool:
        try:
            if ref["kind"] == "app":
                return bool(self._app(ref).Hwnd)
            if ref["kind"] == "workbook":
                return bool(self._workbook(ref).Name)
            return self.resolve(ref["workbook"])
        except Exception:
            return False
