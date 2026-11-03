from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Literal, Protocol

import pyarrow as pa


class ExcelBackend(Protocol):
    active_run_id: str | None

    def connect(
        self,
        mode: Literal["attach_visible", "new_visible", "new_hidden"],
        target: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    def workbook(
        self, app: dict[str, Any], mode: str, name_or_path: str | None = None
    ) -> dict[str, Any]: ...
    def sheet_names(self, workbook: dict[str, Any]) -> list[dict[str, Any]]: ...
    def read_range(
        self,
        workbook: dict[str, Any],
        sheet: str,
        range_spec: str,
        header: bool,
        dtype_hints: dict[str, Any],
    ) -> pa.Table: ...
    def write_table(
        self,
        workbook: dict[str, Any],
        sheet: str,
        start: str,
        table: pa.Table,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]: ...
    def update_cells(
        self, workbook: dict[str, Any], sheet: str, cells: list[dict[str, Any]], allow_formula: bool
    ) -> None: ...
    def manage_sheet(
        self, workbook: dict[str, Any], action: str, name: str, new_name: str | None = None
    ) -> None: ...
    def save(
        self,
        workbook: dict[str, Any],
        mode: str,
        path: Path | None = None,
        fmt: str | None = None,
        overwrite: bool = False,
    ) -> Path | None: ...
    def run_macro(self, workbook: dict[str, Any], macro: str, args: list[Any]) -> Any: ...
    def fast_mode(self, app: dict[str, Any]) -> AbstractContextManager[None]: ...
    def close_app(self, app: dict[str, Any], on_finish: str) -> None: ...
    def resolve(self, ref: dict[str, Any]) -> bool: ...
