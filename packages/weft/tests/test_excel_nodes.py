from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from weft.engine import Engine
from weft.excel import ExcelWorkerSupervisor
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def workflow(excel_backend: str = "fake") -> WorkflowDocument:
    nodes = [
        {
            "id": "n_00000001",
            "type": "flow.trigger",
            "name": "Trigger",
            "position": {"x": 0, "y": 0},
            "params": {},
        },
        {
            "id": "n_00000002",
            "type": "excel.connect",
            "name": "Connect",
            "position": {"x": 0, "y": 0},
            "params": {
                "mode": "attach_visible",
                "target": {"workbook": "汇总.xlsx"},
            },
        },
        {
            "id": "n_00000003",
            "type": "excel.workbook",
            "name": "Workbook",
            "position": {"x": 0, "y": 0},
            "params": {"mode": "open_existing", "name": "汇总.xlsx"},
        },
        {
            "id": "n_00000004",
            "type": "excel.read_range",
            "name": "Read",
            "position": {"x": 0, "y": 0},
            "params": {"sheet": "Sheet1", "range": "A1:B3", "header": True},
        },
    ]
    edges = [
        ("e_00000001", "n_00000002", "app", "n_00000003", "app"),
        ("e_00000002", "n_00000003", "workbook", "n_00000004", "workbook"),
    ]
    if excel_backend == "xlwings":
        nodes[3]["params"]["range"] = "A1:B4"
        nodes.extend(
            [
                {
                    "id": "n_00000005",
                    "type": "table.groupby",
                    "name": "Group",
                    "position": {"x": 0, "y": 0},
                    "params": {
                        "group_by": ["department"],
                        "aggregations": [{"column": "amount", "agg": "sum", "alias": "total"}],
                    },
                },
                {
                    "id": "n_00000006",
                    "type": "excel.write_table",
                    "name": "Write",
                    "position": {"x": 0, "y": 0},
                    "params": {"sheet": "本周", "start": "A1", "mode": "overwrite"},
                },
            ]
        )
        edges.extend(
            [
                ("e_00000003", "n_00000004", "table", "n_00000005", "in"),
                ("e_00000004", "n_00000003", "workbook", "n_00000006", "workbook"),
                ("e_00000005", "n_00000005", "out", "n_00000006", "table"),
            ]
        )
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_ace1000001",
            "name": "excel-nodes",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": [{"node_version": 1, **node} for node in nodes],
            "edges": [
                {
                    "id": edge_id,
                    "source": source,
                    "sourcePort": source_port,
                    "target": target,
                    "targetPort": target_port,
                    "order": 0,
                }
                for edge_id, source, source_port, target, target_port in edges
            ],
        }
    )


def table_output(
    root: Path, run_id: str, node_id: str, port: str = "table"
) -> list[dict[str, Any]]:
    meta = __import__("json").loads(
        (root / ".runs" / run_id / "meta.json").read_text(encoding="utf-8")
    )
    reference = meta["nodes"][node_id]["outputs"][port]
    with pa.memory_map(str(root / reference["path"])) as source:
        return pa.ipc.open_file(source).read_all().to_pylist()


@pytest.mark.integration
@pytest.mark.anyio
async def test_excel_read_is_volatile_across_runs(tmp_path: Path) -> None:
    """US-XLS-11/AC-4; US-XLS-04/AC-6; US-EXE-06/AC-2: changed cells are never cached."""
    worker = ExcelWorkerSupervisor(backend="fake")
    engine = Engine(excel_worker=worker)
    registry = builtin_registry()
    try:
        setup_app = await worker.submit("connect", "new_visible", run_id="setup")
        setup_book = await worker.submit("workbook", setup_app, "new")
        await worker.submit(
            "update_cells",
            setup_book,
            "Sheet1",
            [
                {"address": "A1", "value": "id"},
                {"address": "B1", "value": "amount"},
                {"address": "A2", "value": 1},
                {"address": "B2", "value": 10},
            ],
            False,
            run_id="setup",
        )
        document = workflow()
        document.nodes[1].params["target"]["workbook"] = setup_book["name"]
        document.nodes[2].params["name"] = setup_book["name"]
        first = await engine.run(engine.prepare(document, tmp_path, registry))
        assert table_output(tmp_path, first.run_id, "n_00000004")[0]["amount"] == 10
        assert first.nodes["n_00000004"].from_cache is False
        await worker.submit(
            "update_cells",
            setup_book,
            "Sheet1",
            [{"address": "B2", "value": 99}],
            False,
            run_id="setup",
        )
        second = await engine.run(engine.prepare(document, tmp_path, registry))
        assert table_output(tmp_path, second.run_id, "n_00000004")[0]["amount"] == 99
        assert second.nodes["n_00000004"].from_cache is False
        await worker.submit("close_app", setup_app, "discard", run_id="setup")
    finally:
        engine.close()


@pytest.mark.win_real
@pytest.mark.anyio
async def test_scenario_a_read_group_and_write_visible_excel(tmp_path: Path) -> None:
    """US-XLS-04/AC-6; US-XLS-05/AC-1; scenario A: live read, aggregate and visible writeback."""
    worker = ExcelWorkerSupervisor(backend="xlwings", call_timeout=15)
    engine = Engine(excel_worker=worker)
    app = None
    try:
        app = await worker.submit("connect", "new_visible", run_id="scenario-setup")
        workbook = await worker.submit("workbook", app, "new")
        await worker.submit("save", workbook, "save_as", tmp_path / "汇总.xlsx", "xlsx", False)
        workbook = await worker.submit("workbook", app, "open_existing", "汇总.xlsx")
        table = pa.Table.from_pylist(
            [
                {"department": "华东", "amount": 10},
                {"department": "华东", "amount": 15},
                {"department": "华北", "amount": 7},
            ]
        )
        written = await worker.submit(
            "write_table", workbook, "Sheet1", "A1", table, "overwrite", {"header": True}
        )
        initial = await worker.submit("read_range", workbook, "Sheet1", "A1:B4", True, {})
        assert len(initial.to_pylist()) == 3, (written, initial.to_pylist())
        record = await engine.run(engine.prepare(workflow("xlwings"), tmp_path, builtin_registry()))
        assert record.status == "succeeded"
        assert record.nodes["n_00000006"].status == "executed"
        result = await worker.submit("read_range", workbook, "本周", "A1:B3", True, {})
        actual = {row["department"]: row["total"] for row in result.to_pylist()}
        assert actual == {"华东": 25, "华北": 7}, (
            table_output(tmp_path, record.run_id, "n_00000004"),
            table_output(tmp_path, record.run_id, "n_00000005", "out"),
            result.to_pylist(),
        )
        await worker.submit("close_app", app, "discard")
        app = None
    finally:
        if app is not None:
            await worker.submit("close_app", app, "discard")
        engine.close()
