from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest
from weft.agent.node_tool import NodeTool, validate_node_tools
from weft.engine import Engine
from weft.nodes.registry import builtin_registry
from weft.worker import WorkflowEnvironment
from weft.worker.pool import WorkerPool
from weft.workflow import WorkflowDocument


def document() -> WorkflowDocument:
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_bb10000001",
            "name": "node-tool",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": [
                {
                    "id": "n_00000001",
                    "type": "flow.trigger",
                    "name": "Trigger",
                    "node_version": 1,
                    "position": {"x": 0, "y": 0},
                    "params": {},
                },
                {
                    "id": "n_00000002",
                    "type": "table.creator",
                    "name": "Input",
                    "node_version": 1,
                    "position": {"x": 0, "y": 0},
                    "params": {"rows": [{"amount": 1}, {"amount": 3}, {"amount": 2}]},
                },
                {
                    "id": "n_00000003",
                    "type": "table.row_filter",
                    "name": "Filter",
                    "node_version": 1,
                    "position": {"x": 0, "y": 0},
                    "params": {"column": "amount", "operator": ">", "value": 1},
                },
                {
                    "id": "n_00000004",
                    "type": "agent.node_tool",
                    "name": "Filter tool",
                    "node_version": 1,
                    "position": {"x": 0, "y": 0},
                    "params": {
                        "target_node": "n_00000003",
                        "tool_name": "filter_rows",
                        "description": "Filter rows",
                        "exposed_params": ["column", "operator"],
                        "result_format": "json",
                    },
                },
            ],
            "edges": [
                {
                    "id": "e_00000001",
                    "source": "n_00000002",
                    "sourcePort": "out",
                    "target": "n_00000003",
                    "targetPort": "in",
                    "order": 0,
                },
            ],
        }
    )


def descriptor() -> dict[str, Any]:
    return {
        "kind": "node",
        "name": "filter_rows",
        "description": "Filter rows",
        "binding": {"target_node": "n_00000003"},
        "exposed_params": ["column", "operator"],
        "result_format": "json",
    }


@pytest.mark.integration
def test_node_tool_uses_frozen_snapshot_and_real_run_pool(tmp_path: Path) -> None:
    """US-AGT-04/AC-1,3,4,5: real Worker tool uses frozen params and no global cache."""
    runpy.run_path("packages/weft/tests/test_worker_pool.py")["make_workflow"](tmp_path)
    environment = WorkflowEnvironment(tmp_path)
    environment.sync()
    engine = Engine(lambda root, run_id: WorkerPool(environment, run_id))
    registry = builtin_registry()
    original = document()
    prepared = engine.prepare(original, tmp_path, registry)
    original.nodes[2].params["value"] = 999
    try:
        record = asyncio_run(engine, prepared)
        assert record.status == "succeeded"
        original_outputs = record.nodes["n_00000003"].outputs.copy()
        cache_meta = tmp_path / ".runs" / "cache" / "n_00000003" / "meta.json"
        cache_before = cache_meta.read_bytes()
        tool = NodeTool(prepared, engine, descriptor(), "n_00000004")
        result = json.loads(tool.invoke({"operator": ">"}))
        assert [row["amount"] for row in result] == [3, 2]
        assert tool.parameters["additionalProperties"] is False
        assert set(tool.parameters["properties"]) == {"column", "operator"}
        assert record.nodes["n_00000003"].outputs == original_outputs
        assert cache_meta.read_bytes() == cache_before
        assert engine.worker_pools[record.run_id].process_ids
    finally:
        engine.close()


def asyncio_run(engine: Engine, prepared: Any) -> Any:
    import asyncio

    return asyncio.run(engine.run(prepared))


def test_node_tool_rejects_unauthorized_whitelist_side_effect_and_recursion(
    tmp_path: Path,
) -> None:
    """US-AGT-04/AC-2,6,7: unauthorized code, extra params and recursion are denied."""
    registry = builtin_registry()
    invalid = document()
    invalid.nodes[2].type = "code.python"
    with pytest.raises(PermissionError, match="not an authorized"):
        validate_node_tools(invalid, registry)

    invalid = document()
    invalid.nodes[3].params["exposed_params"] = ["path"]
    with pytest.raises(PermissionError, match="whitelist"):
        validate_node_tools(invalid, registry)

    invalid = document()
    invalid.nodes[2].type = "excel.write_table"
    invalid.nodes[2].params = {"sheet": "out", "start": "A1", "mode": "overwrite"}
    invalid.edges = []
    invalid.nodes[3].params.update(
        {
            "allow_side_effects": True,
            "require_confirmation": True,
        }
    )
    prepared = Engine().prepare(invalid, tmp_path / "side", registry)
    side_descriptor = descriptor()
    side_descriptor.update(
        {"exposed_params": ["sheet"], "allow_side_effects": True, "require_confirmation": True}
    )
    tool = NodeTool(prepared, Engine(), side_descriptor, "n_00000004")
    with pytest.raises(PermissionError, match="confirmation"):
        tool.invoke({"sheet": "Dashboard"})

    from weft.workflow.models import Edge

    invalid = document()
    prepared = Engine().prepare(invalid, tmp_path / "cycle", registry)
    prepared.workflow.edges.append(
        Edge.model_validate(
            {
                "id": "e_00000003",
                "source": "n_00000004",
                "sourcePort": "tools",
                "target": "n_00000003",
                "targetPort": "variables",
                "order": 0,
            }
        )
    )
    with pytest.raises(ValueError, match="ancestors"):
        NodeTool(prepared, Engine(), descriptor(), "n_00000004")


def test_node_tool_requires_materialized_upstream(tmp_path: Path) -> None:
    """US-AGT-04/AC-4: missing upstream snapshots fail instead of executing implicit work."""
    prepared = Engine().prepare(document(), tmp_path, builtin_registry())
    with pytest.raises(ValueError, match="Upstream of 'n_00000002' not executed"):
        NodeTool(prepared, Engine(), descriptor(), "n_00000004").invoke({"operator": ">"})


def test_save_api_rejects_unauthorized_node_tool(tmp_path: Path) -> None:
    """US-AGT-04/AC-7: persistence rejects unauthorized targets before writing."""
    from fastapi.testclient import TestClient
    from weft.api.app import create_app
    from weft.api.security import Session

    invalid = document()
    invalid.nodes[2].type = "code.python"
    (tmp_path / "workflow.json").write_text(invalid.model_dump_json(), encoding="utf-8")
    app = create_app(session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"))
    app.state.roots[invalid.id] = tmp_path
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        response = client.put(
            f"/api/workflows/{invalid.id}",
            json=invalid.model_dump(mode="json"),
            headers={"Authorization": "Bearer test", "X-Weft-Client": "ui"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NODE_TOOL_NOT_AUTHORIZED"


def test_tool_ports_expose_no_graph_mutation_capability() -> None:
    """US-AGT-11/AC-1: only the two controlled tool providers exist, with no graph mutation API."""
    from weft.agent.sandbox_tools import SandboxedTool

    producers = {
        node.type
        for node in builtin_registry().all()
        if any(port.kind == "tool" for port in node.outputs)
    }
    assert producers == {"agent.node_tool", "agent.sandboxed_tools"}
    for name in (
        "add_node",
        "delete_node",
        "create_edge",
        "delete_edge",
        "update_workflow",
        "save_workflow",
    ):
        assert not hasattr(NodeTool, name)
        assert not hasattr(SandboxedTool, name)
