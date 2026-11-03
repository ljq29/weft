from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from weft.engine import Engine
from weft.excel import ExcelWorkerError, ExcelWorkerSupervisor
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument


def document(macro: str) -> WorkflowDocument:
    nodes = [
        ("n_00000001", "flow.trigger", {}),
        ("n_00000002", "excel.connect", {"mode": "attach_visible"}),
        ("n_00000003", "excel.workbook", {"mode": "new"}),
        ("n_00000004", "excel.run_macro", {"macro": macro, "args": [1, "x"]}),
    ]
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_ace1000001",
            "name": "excel-macro",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": [
                {
                    "id": node_id,
                    "type": node_type,
                    "node_version": 1,
                    "name": node_type,
                    "position": {"x": 0, "y": 0},
                    "params": params,
                }
                for node_id, node_type, params in nodes
            ],
            "edges": [
                {
                    "id": "e_00000001",
                    "source": "n_00000002",
                    "sourcePort": "app",
                    "target": "n_00000003",
                    "targetPort": "app",
                    "order": 0,
                },
                {
                    "id": "e_00000002",
                    "source": "n_00000003",
                    "sourcePort": "workbook",
                    "target": "n_00000004",
                    "targetPort": "workbook",
                    "order": 0,
                },
            ],
        }
    )


@pytest.mark.integration
def test_excel_macro_value_and_com_error(tmp_path: Path) -> None:
    """US-XLS-09/AC-1,2: Fake contract returns values and surfaces COM failures."""
    worker = ExcelWorkerSupervisor(backend="fake")
    try:
        for macro in ("Module1.Refresh", "Missing"):
            engine = Engine(excel_worker=worker)

            record = asyncio.run(
                engine.run(engine.prepare(document(macro), tmp_path, builtin_registry()))
            )
            if macro == "Missing":
                assert record.status == "failed"
                assert "COM error" in record.nodes["n_00000004"].error["message"]
            else:
                assert record.status == "succeeded"
                assert record.nodes["n_00000004"].outputs["variable"].inline == {
                    "macro": macro,
                    "args": [1, "x"],
                }
    finally:
        worker.close()


@pytest.mark.win_real
def test_real_excel_missing_macro_reports_com_error(tmp_path: Path) -> None:
    """US-XLS-09/AC-2: real Excel surfaces a missing macro COM error."""
    worker = ExcelWorkerSupervisor(backend="xlwings", call_timeout=10)

    async def scenario() -> None:
        app = await worker.submit("connect", "new_hidden", run_id="macro-real")
        workbook = await worker.submit("workbook", app, "new", run_id="macro-real")
        with pytest.raises(ExcelWorkerError, match="WeftMissingMacro"):
            await worker.submit("run_macro", workbook, "WeftMissingMacro", [], run_id="macro-real")

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(worker.release_run("macro-real", on_finish="discard"))
        worker.close()
