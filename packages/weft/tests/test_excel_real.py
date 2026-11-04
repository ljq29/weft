from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pyarrow as pa
import pytest
from weft.excel import ExcelWorkerError, ExcelWorkerSupervisor
from weft.excel.targets import ExcelTargetStore


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_excel_target_store_persists_stable_and_runtime_hints(tmp_path: Path) -> None:
    """US-XLS-01/AC-3,4: user-level targets persist stable identity, not workflow data."""
    store = ExcelTargetStore(tmp_path / "excel-targets.toml")
    store.save(
        "workflow",
        "connect",
        {"workbook": "ref.xlsx", "pid": 1234, "window_title": "ref.xlsx - Excel", "ignored": "x"},
    )
    target = store.get("workflow", "connect")
    assert target["workbook"] == "ref.xlsx"
    assert target["pid"] == 1234
    assert "ignored" not in target


@pytest.mark.win_real
@pytest.mark.anyio
async def test_real_excel_workbook_read_write_update_sheet_and_save(tmp_path: Path) -> None:
    """US-XLS-01/AC-1..4; US-XLS-02/AC-1..3; US-XLS-03/AC-1..4: real Excel contract.

    US-XLS-04/AC-1..6; US-XLS-05/AC-1..6; US-XLS-06/AC-1..3.
    US-XLS-07/AC-1..3; US-XLS-08/AC-1..4.
    """
    worker = ExcelWorkerSupervisor(backend="xlwings", call_timeout=10)
    app: dict[str, object] | None = None
    try:
        app = await worker.submit("connect", "new_hidden", run_id="excel-real")
        assert app["visible"] is False
        assert app["owned"] is True
        assert app["process_created_at"]
        workbook = await worker.submit("workbook", app, "new", run_id="excel-real")
        assert workbook["saved"] is False
        table = pa.Table.from_pylist(
            [
                {"id": 1, "amount": 2.5, "note": "=1+1", "empty": None},
                {"id": 2, "amount": 3, "note": "正常", "empty": None},
            ]
        )
        await worker.submit(
            "write_table",
            workbook,
            "Sheet1",
            "A1",
            table,
            "overwrite",
            {"header": True, "clear_below": True},
        )
        result = await worker.submit("read_range", workbook, "Sheet1", "A1:D3", True, {})
        assert result.to_pylist()[0] == {
            "id": 1,
            "amount": 2.5,
            "note": "=1+1",
            "empty": None,
        }
        with pytest.raises(ExcelWorkerError):
            await worker.submit(
                "update_cells",
                workbook,
                "Sheet1",
                [{"address": "B4", "value": 9}, {"address": "invalid", "value": 1}],
                False,
            )
        unchanged = await worker.submit("read_range", workbook, "Sheet1", "B4", False, {})
        assert all(value is None for row in unchanged.to_pylist() for value in row.values())
        await worker.submit(
            "update_cells", workbook, "Sheet1", [{"address": "B4", "value": 9}], False
        )
        await worker.submit("write_table", workbook, "Sheet1", "A1", table, "append", {})
        assert (
            await worker.submit("read_range", workbook, "Sheet1", "A1:A5", True, {})
        ).num_rows == 4
        await worker.submit("manage_sheet", workbook, "create", "Data")
        await worker.submit("manage_sheet", workbook, "rename", "Data", "Renamed")
        assert "Renamed" in {item["name"] for item in await worker.submit("sheet_names", workbook)}
        await worker.submit("manage_sheet", workbook, "delete", "Renamed")
        with pytest.raises(ExcelWorkerError, match="工作表不存在"):
            await worker.submit("read_range", workbook, "Missing", "A1", True, {})
        with pytest.raises(ExcelWorkerError, match="最后一张"):
            await worker.submit("manage_sheet", workbook, "delete", "Sheet1")
        await worker.submit(
            "update_cells", workbook, "Sheet1", [{"address": "E1", "value": "=1+1"}], True
        )
        formula = await worker.submit("read_range", workbook, "Sheet1", "E1", False, {})
        assert formula.to_pylist()[0]["Column_1"] == 2
        with pytest.raises(ExcelWorkerError, match="save_as"):
            await worker.submit("save", workbook, "save")
        path = tmp_path / "out" / "result.xlsx"
        assert await worker.submit("save", workbook, "save_as", path, "xlsx", False) == path
        opened = await worker.submit("workbook", app, "open_file", str(path))
        assert Path(opened["path"]) == path
        await worker.submit(
            "update_cells", opened, "Sheet1", [{"address": "F1", "value": "shared"}], False
        )
        shared = await worker.submit("read_range", workbook, "Sheet1", "F1", False, {})
        assert shared.to_pylist() == [{"Column_1": "shared"}]
        with pytest.raises(ExcelWorkerError):
            await worker.submit("save", workbook, "save_as", path, "xlsx", False)
        assert await worker.submit("resolve", workbook) is True
        pid = app["pid"]
        await worker.release_run("excel-real", on_finish="discard")
        app = None
        from weft.excel.xlwings_backend import process_alive

        for _ in range(50):
            if not process_alive(int(pid)):
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("owned hidden Excel did not exit")
    finally:
        if app is not None:
            await worker.submit("close_app", app, "discard")
        worker.close()


@pytest.mark.win_real
@pytest.mark.benchmark
@pytest.mark.anyio
async def test_real_excel_bulk_read_write_benchmark() -> None:
    """US-XLS-04/AC-4; US-XLS-05/AC-5: record real whole-range 100k-cell timings."""
    worker = ExcelWorkerSupervisor(backend="xlwings", call_timeout=10)
    app = None
    try:
        app = await worker.submit("connect", "new_hidden", run_id="excel-benchmark")
        workbook = await worker.submit("workbook", app, "new", run_id="excel-benchmark")
        table = pa.table(
            {f"c{column}": [row * 100 + column for row in range(1000)] for column in range(100)}
        )
        started = time.perf_counter()
        await worker.submit(
            "write_table", workbook, "Sheet1", "A1", table, "overwrite", {"header": False}
        )
        write_seconds = time.perf_counter() - started
        started = time.perf_counter()
        result = await worker.submit("read_range", workbook, "Sheet1", "A1:CV1000", False, {})
        read_seconds = time.perf_counter() - started
        assert result.num_rows == 1000 and result.num_columns == 100
        report = {
            "write_seconds": write_seconds,
            "read_seconds": read_seconds,
            "rows": 1000,
            "cols": 100,
        }
        output = Path(".test-reports/excel-backend-benchmark.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        if app is not None:
            await worker.submit("close_app", app, "discard")
        worker.close()


@pytest.mark.win_real
def test_real_visible_attach_fast_mode_restore_and_dates() -> None:
    """US-XLS-01/AC-1..4; US-XLS-04/AC-3; US-XLS-10/AC-1,2: visible Excel contract."""
    from datetime import datetime

    import pythoncom
    from weft.excel.xlwings_backend import XlwingsBackend, excel_value

    pythoncom.CoInitialize()
    backend = XlwingsBackend()
    backend.active_run_id = "excel-visible"
    app = backend.connect("new_visible")
    application = None
    sheet = None
    try:
        workbook = backend.workbook(app, "new")
        attached = backend.connect(
            "attach_visible", {"pid": app["pid"], "workbook": workbook["name"]}
        )
        assert attached["pid"] == app["pid"] and attached["owned"] is False
        application = backend._app(app)
        previous = (application.ScreenUpdating, application.Calculation, application.EnableEvents)
        with backend.fast_mode(app):
            assert application.ScreenUpdating is False
            assert application.EnableEvents is False
        assert (
            application.ScreenUpdating,
            application.Calculation,
            application.EnableEvents,
        ) == previous
        sheet = backend._sheet(workbook, "Sheet1")
        sheet.Range("A1").Value2 = excel_value(datetime(2026, 1, 2, 3, 4, 5))
        sheet.Range("A1").NumberFormat = "yyyy-mm-dd hh:mm:ss"
        result = backend.read_range(workbook, "Sheet1", "A1", False, {})
        assert result.to_pylist() == [{"Column_1": datetime(2026, 1, 2, 3, 4, 5)}]
    finally:
        application = None
        sheet = None
        backend.close_app(app, "discard")
        pythoncom.CoUninitialize()
