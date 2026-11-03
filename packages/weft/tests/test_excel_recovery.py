from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from weft.excel import (
    ExcelWorkerError,
    ExcelWorkerRestartedError,
    ExcelWorkerSupervisor,
)
from weft.excel.xlwings_backend import ExcelBusyError, XlwingsBackend


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_missing_excel_registration_fails_promptly(monkeypatch: pytest.MonkeyPatch) -> None:
    """US-XLS-12/AC-1: missing COM registration returns a clear error within one second."""
    import winreg

    def missing(*args: Any) -> None:
        raise FileNotFoundError("Excel.Application")

    monkeypatch.setattr(winreg, "OpenKey", missing)
    backend = XlwingsBackend.__new__(XlwingsBackend)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="Excel is not installed or not registered"):
        backend.connect("new_hidden")
    assert time.monotonic() - started < 1


def test_excel_busy_retries_three_times(monkeypatch: pytest.MonkeyPatch) -> None:
    """US-XLS-12/AC-2: rejected COM calls retry three times with a readable error."""
    monkeypatch.setattr(time, "sleep", lambda _: None)
    backend = XlwingsBackend.__new__(XlwingsBackend)
    calls = 0

    def rejected() -> None:
        nonlocal calls
        calls += 1
        error = RuntimeError("Call was rejected by callee")
        error.hresult = -2147418111  # type: ignore[attr-defined]
        raise error

    with pytest.raises(ExcelBusyError, match=r"Excel is busy \(modal dialog open\?\)"):
        backend._retry(rejected)
    assert calls == 3


@pytest.mark.win_real
@pytest.mark.anyio
async def test_real_wedged_worker_recovers_without_replaying_or_killing_user_excel() -> None:
    """US-XLS-12/AC-5: a real modal COM call wedges, restarts, and never replays writes."""
    worker = ExcelWorkerSupervisor(backend="xlwings", call_timeout=0.1, restart_after_timeouts=2)
    app = None
    try:
        app = await worker.submit("connect", "new_hidden", run_id="excel-wedged", timeout=5)
        first = asyncio.create_task(worker.submit("probe", app, modal=True))
        await asyncio.sleep(0.03)
        second = asyncio.create_task(worker.submit("probe", app))
        await asyncio.sleep(0.05)
        queued = asyncio.create_task(worker.submit("probe"))
        with pytest.raises(TimeoutError):
            await first
        with pytest.raises(TimeoutError):
            await second
        with pytest.raises(ExcelWorkerRestartedError) as error:
            await queued
        assert error.value.code == "EXCEL_WORKER_RESTARTED"
        recovered = await worker.submit("probe", timeout=3)
        assert recovered["modal"] is False
        from weft.excel.xlwings_backend import process_alive

        for _ in range(30):
            if not process_alive(app["pid"]):
                break
            await asyncio.sleep(0.1)
        assert not process_alive(app["pid"])
        app = None
    finally:
        if app is not None:
            try:
                await worker.submit("close_app", app, "discard", timeout=3)
            except (ExcelWorkerError, TimeoutError):
                pass
        worker.close()
