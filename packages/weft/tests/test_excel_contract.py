from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest
from weft.excel.fake import FakeExcelBackend


@pytest.fixture
def backend() -> FakeExcelBackend:
    return FakeExcelBackend()


def test_workbook_modes_are_consistent(backend: FakeExcelBackend, tmp_path: Path) -> None:
    """US-XLS-03/AC-4: open-existing, open-file and new workbook modes share the contract."""
    app = backend.connect("new_hidden")
    new = backend.workbook(app, "new")
    assert new["saved"] is False
    existing = backend.workbook(app, "open_existing", new["name"])
    assert existing["id"] == new["id"]
    path = tmp_path / "ref.xlsx"
    path.write_bytes(b"ref")
    opened = backend.workbook(app, "open_file", str(path))
    assert backend.workbook(app, "open_file", str(path))["id"] == opened["id"]
    with pytest.raises(ValueError, match="工作簿未打开"):
        backend.workbook(app, "open_existing", "missing.xlsx")


def test_write_read_types_formula_overwrite_and_append(backend: FakeExcelBackend) -> None:
    """US-XLS-03/AC-4; US-XLS-04/AC-6: fake preserves reads, formulas and writes."""
    app = backend.connect("new_visible")
    workbook = backend.workbook(app, "new")
    table = pa.Table.from_pylist([{"id": 1, "value": 2.5, "note": "=SUM(A1:A2)", "empty": None}])
    backend.write_table(
        workbook, "Sheet1", "A1", table, "overwrite", {"header": True, "clear_below": True}
    )
    result = backend.read_range(workbook, "Sheet1", "A1:D2", True, {})
    assert result.to_pylist()[0]["note"] == "'=SUM(A1:A2)"
    backend.write_table(workbook, "Sheet1", "A1", table, "append", {"header": True})
    assert backend.read_range(workbook, "Sheet1", "A1:D3", True, {}).num_rows == 2
    backend.write_table(
        workbook,
        "Sheet1",
        "A1",
        pa.Table.from_pylist([{"id": 9, "value": 0.0, "note": "x", "empty": None}]),
        "overwrite",
        {"header": True, "clear_below": True},
    )
    assert backend.read_range(workbook, "Sheet1", "A1:D2", True, {}).to_pylist()[0]["id"] == 9


def test_cell_update_is_atomic_and_sheet_lifecycle_is_safe(backend: FakeExcelBackend) -> None:
    """US-XLS-03/AC-4: cell updates are atomic; sheet operations follow the contract."""
    app = backend.connect("new_hidden")
    workbook = backend.workbook(app, "new")
    with pytest.raises(ValueError):
        backend.update_cells(
            workbook,
            "Sheet1",
            [{"address": "B2", "value": 42}, {"address": "bad", "value": 1}],
            False,
        )
    assert backend.read_range(workbook, "Sheet1", "B2", True, {}).num_rows == 0
    backend.manage_sheet(workbook, "create", "Data")
    backend.manage_sheet(workbook, "rename", "Data", "Renamed")
    assert backend.sheet_names(workbook)[-1]["name"] == "Renamed"
    backend.manage_sheet(workbook, "delete", "Renamed")
    with pytest.raises(ValueError):
        backend.manage_sheet(workbook, "delete", "Sheet1")
    assert backend.resolve(workbook) is True
    backend.close_app(app, "discard")
    assert backend.resolve(workbook) is False
