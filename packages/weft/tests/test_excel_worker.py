from __future__ import annotations

import asyncio
import os

import pyarrow as pa
import pytest
from weft.excel import (
    ExcelWorkerRestartedError,
    ExcelWorkerSupervisor,
    FakeExcelBackend,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.integration
@pytest.mark.anyio
async def test_backend_calls_share_sta_thread_and_run_references() -> None:
    """US-XLS-11/AC-1,3: real child process serializes backend calls and resolves refs."""
    worker = ExcelWorkerSupervisor(backend="fake")
    worker.start()
    try:
        app = await worker.submit("connect", "new_hidden", run_id="run_excel")
        workbook = await worker.submit("workbook", app, "new", run_id="run_excel")
        table = pa.Table.from_pylist([{"id": 1}, {"id": 2}])
        await worker.submit(
            "write_table",
            workbook,
            "Sheet1",
            "A1",
            table,
            "overwrite",
            {"header": True},
            run_id="run_excel",
        )
        result = await worker.submit(
            "read_range", workbook, "Sheet1", "A1:A3", True, {}, run_id="run_excel"
        )
        assert result.to_pylist() == [{"id": 1}, {"id": 2}]
        first = await worker.submit("probe")
        second = await worker.submit("probe")
        assert first["pid"] != os.getpid()
        assert first["pid"] == second["pid"]
        assert first["thread_id"] == second["thread_id"]
        assert first["thread_name"] == "ExcelSTA"
        assert await worker.submit("resolve", workbook) is True
        await worker.release_run("run_excel", on_finish="discard")
        assert await worker.submit("resolve", workbook) is False
    finally:
        worker.close()


@pytest.mark.integration
@pytest.mark.anyio
async def test_independent_hosts_globally_serialize_excel_calls() -> None:
    """US-XLS-11/AC-2: independent worker processes acquire the same global mutex."""
    first = ExcelWorkerSupervisor(backend="fake")
    second = ExcelWorkerSupervisor(backend="fake")
    first.start()
    second.start()
    try:
        left, right = await asyncio.gather(first.submit("probe", 0.2), second.submit("probe", 0.2))
        assert left["pid"] != right["pid"]
        assert left["end"] <= right["start"] or right["end"] <= left["start"]
    finally:
        first.close()
        second.close()


@pytest.mark.integration
@pytest.mark.anyio
async def test_timeout_is_busy_then_restart_fails_queued_without_replay() -> None:
    """US-XLS-11/AC-5; US-XLS-12/AC-3: timeout keeps busy; queued work is never replayed."""
    worker = ExcelWorkerSupervisor(backend="fake", call_timeout=0.05, restart_after_timeouts=2)
    worker.start()
    try:
        initial = await worker.submit("probe")
        first = asyncio.create_task(worker.submit("probe", 5))
        await asyncio.sleep(0.02)
        second = asyncio.create_task(worker.submit("probe", 5))
        await asyncio.sleep(0.045)
        assert worker.busy is True
        queued = asyncio.create_task(worker.submit("probe", 0))
        with pytest.raises(TimeoutError, match="still busy"):
            await first
        with pytest.raises(TimeoutError):
            await second
        with pytest.raises(ExcelWorkerRestartedError) as error:
            await queued
        assert error.value.code == "EXCEL_WORKER_RESTARTED"
        result = await worker.submit("probe", 0, timeout=2)
        assert result["pid"] != initial["pid"]
        assert await worker.submit("resolve", {"kind": "app", "pid": 1}) is False
    finally:
        worker.close()


def test_fast_mode_restores_state() -> None:
    """US-XLS-11/AC-1,3: backend fast-mode context restores state and registered refs."""
    backend = FakeExcelBackend()
    app = backend.connect("new_visible")
    app["fast_mode"] = "original"
    with backend.fast_mode(app):
        assert app["fast_mode"] is True
    assert app["fast_mode"] == "original"
