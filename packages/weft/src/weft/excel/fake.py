from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa


def cell(address: str) -> tuple[int, int]:
    match = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", address.upper())
    if not match:
        raise ValueError(f"Invalid cell address: {address}")
    letters, row = match.groups()
    column = 0
    for letter in letters:
        column = column * 26 + ord(letter) - ord("A") + 1
    return int(row), column


def column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


class FakeExcelBackend:
    def __init__(self) -> None:
        self.active_run_id: str | None = None
        self.apps: dict[int, dict[str, Any]] = {}
        self.workbooks: dict[str, dict[str, Any]] = {}
        self._pid = 1000
        self._workbook = 0

    def connect(self, mode: str, target: dict[str, Any] | None = None) -> dict[str, Any]:
        if mode == "attach_visible":
            candidates = [item for item in self.apps.values() if item["ref"]["visible"]]
            if target:
                candidates = [
                    item
                    for item in candidates
                    if (target.get("pid") is None or item["ref"]["pid"] == target["pid"])
                    and (
                        not target.get("workbook")
                        or target["workbook"] in [book["ref"]["name"] for book in item["workbooks"]]
                    )
                ]
            if len(candidates) == 1:
                ref: dict[str, Any] = candidates[0]["ref"].copy()
                ref["owned"] = False
                ref["workbooks"] = [book["ref"]["name"] for book in candidates[0]["workbooks"]]
                return ref
            if target:
                raise ValueError("Saved Excel target cannot be resolved uniquely")
            mode = "new_visible"
        self._pid += 1
        app = {
            "kind": "app",
            "pid": self._pid,
            "visible": mode != "new_hidden",
            "owned": mode != "attach_visible",
            "workbooks": [],
        }
        self.apps[self._pid] = {"ref": app, "workbooks": []}
        return app

    def workbook(
        self, app: dict[str, Any], mode: str, name_or_path: str | None = None
    ) -> dict[str, Any]:
        current: list[dict[str, Any]] = self.apps[app["pid"]]["workbooks"]
        if mode == "open_existing":
            for workbook in current:
                ref: dict[str, Any] = workbook["ref"]
                if ref["name"] == name_or_path:
                    return ref
            raise ValueError(
                f"工作簿未打开：{name_or_path}；已打开：{[item['ref']['name'] for item in current]}"
            )
        if mode == "open_file":
            for workbook in current:
                ref = workbook["ref"]
                if ref.get("path") == name_or_path:
                    return ref
            if not Path(name_or_path or "").exists():
                raise FileNotFoundError(name_or_path)
        self._workbook += 1
        name: str = (
            name_or_path if mode == "open_file" and name_or_path else f"Book{self._workbook}"
        )
        ref = {
            "kind": "workbook",
            "app_pid": app["pid"],
            "name": Path(name).name,
            "path": name_or_path if mode == "open_file" else None,
            "saved": mode == "open_file",
            "id": f"wb_{self._workbook}",
        }
        workbook = {"ref": ref, "sheets": {"Sheet1": {"cells": {}, "visible": True}}}
        current.append(workbook)
        self.workbooks[ref["id"]] = workbook
        return ref

    def sheet_names(self, workbook: dict[str, Any]) -> list[dict[str, Any]]:
        sheets = self.workbooks[workbook["id"]]["sheets"]
        return [
            {"name": name, "index": index + 1, "visible": sheet["visible"]}
            for index, (name, sheet) in enumerate(sheets.items())
        ]

    def read_range(
        self,
        workbook: dict[str, Any],
        sheet: str,
        range_spec: str,
        header: bool,
        dtype_hints: dict[str, Any],
    ) -> pa.Table:
        cells = self.workbooks[workbook["id"]]["sheets"][sheet]["cells"]
        if range_spec:
            start, end = range_spec.split(":", 1) if ":" in range_spec else (range_spec, range_spec)
            row1, col1 = cell(start)
            row2, col2 = cell(end)
        elif cells:
            row1, col1 = (
                min(cell(address)[0] for address in cells),
                min(cell(address)[1] for address in cells),
            )
            row2, col2 = (
                max(cell(address)[0] for address in cells),
                max(cell(address)[1] for address in cells),
            )
        else:
            return pa.Table.from_pylist([])
        rows = [
            [cells.get(f"{column_name(column)}{row}") for column in range(col1, col2 + 1)]
            for row in range(row1, row2 + 1)
        ]
        if header and rows:
            names = [str(value or f"Column_{index}") for index, value in enumerate(rows.pop(0))]
            data = {name: [row[index] for row in rows] for index, name in enumerate(names)}
        else:
            data = {
                column_name(index): [row[index] for row in rows] for index in range(col2 - col1 + 1)
            }
        return pl.DataFrame(data).to_arrow()

    def write_table(
        self,
        workbook: dict[str, Any],
        sheet: str,
        start: str,
        table: pa.Table,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        workbook_data = self.workbooks[workbook["id"]]
        if sheet not in workbook_data["sheets"]:
            workbook_data["sheets"][sheet] = {"cells": {}, "visible": True}
        cells = workbook_data["sheets"][sheet]["cells"]
        frame = pl.DataFrame(table)
        start_row, start_column = cell(start)
        if mode == "append":
            existing = [cell(address)[0] for address in cells if cell(address)[1] == start_column]
            start_row = max(existing, default=start_row - 1) + 1
        rows: list[tuple[Any, ...]] = list(frame.iter_rows())
        values: list[list[Any]] = (
            [frame.columns, *[list(row) for row in rows]]
            if options.get("header", True) and mode != "append"
            else [list(row) for row in rows]
        )
        if mode == "overwrite" and options.get("clear_below", True):
            for address in list(cells):
                target_row, column = cell(address)
                if target_row >= start_row and start_column <= column < start_column + frame.width:
                    del cells[address]
        for row_index, row in enumerate(values):
            for column_index, value in enumerate(row):
                if (
                    isinstance(value, str)
                    and value.startswith("=")
                    and not options.get("allow_formula", False)
                ):
                    value = "'" + value
                cells[f"{column_name(start_column + column_index)}{start_row + row_index}"] = value
        return {
            "kind": "range",
            "workbook": workbook,
            "sheet": sheet,
            "address": start,
            "rows": len(values),
            "cols": frame.width,
        }

    def update_cells(
        self, workbook: dict[str, Any], sheet: str, cells: list[dict[str, Any]], allow_formula: bool
    ) -> None:
        for item in cells:
            cell(item["address"])
        target = self.workbooks[workbook["id"]]["sheets"][sheet]["cells"]
        for item in cells:
            value = item["value"]
            if isinstance(value, str) and value.startswith("=") and not allow_formula:
                value = "'" + value
            target[item["address"]] = value

    def manage_sheet(
        self, workbook: dict[str, Any], action: str, name: str, new_name: str | None = None
    ) -> None:
        sheets = self.workbooks[workbook["id"]]["sheets"]
        if action == "create":
            sheets[name] = {"cells": {}, "visible": True}
        elif action == "delete":
            if len(sheets) == 1:
                raise ValueError("不能删除最后一张工作表")
            del sheets[name]
        elif action == "rename":
            sheets[new_name or name] = sheets.pop(name)
        elif action == "clear":
            sheets[name]["cells"] = {}

    def save(
        self,
        workbook: dict[str, Any],
        mode: str,
        path: Path | None = None,
        fmt: str | None = None,
        overwrite: bool = False,
    ) -> Path | None:
        ref = self.workbooks[workbook["id"]]["ref"]
        if mode == "save" and not ref.get("path"):
            raise ValueError("未保存工作簿请使用 save_as")
        target = path or Path(ref["path"])
        if target.exists() and not overwrite and mode == "save_as":
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fake-excel", encoding="utf-8")
        ref["path"] = str(target)
        ref["saved"] = True
        return target

    def run_macro(self, workbook: dict[str, Any], macro: str, args: list[Any]) -> Any:
        if macro in {"Missing", "Raise"}:
            raise RuntimeError(f"COM error: macro '{macro}' does not exist or raised VBA error")
        return {"macro": macro, "args": args}

    @contextmanager
    def fast_mode(self, app: dict[str, Any]) -> Iterator[None]:
        previous = app.get("fast_mode", False)
        app["fast_mode"] = True
        try:
            yield
        finally:
            app["fast_mode"] = previous

    def close_app(self, app: dict[str, Any], on_finish: str) -> None:
        workbook_ids = [
            item["ref"]["id"] for item in self.apps.get(app["pid"], {}).get("workbooks", [])
        ]
        for workbook_id in workbook_ids:
            self.workbooks.pop(workbook_id, None)
        self.apps.pop(app["pid"], None)

    def probe(self, delay: float = 0) -> dict[str, Any]:
        start = time.monotonic()
        time.sleep(delay)
        return {
            "pid": os.getpid(),
            "thread_id": threading.get_ident(),
            "thread_name": threading.current_thread().name,
            "start": start,
            "end": time.monotonic(),
        }

    def resolve(self, ref: dict[str, Any]) -> bool:
        if ref["kind"] == "app":
            return ref["pid"] in self.apps
        if ref["kind"] == "workbook":
            return ref["id"] in self.workbooks
        return self.resolve(ref["workbook"])
