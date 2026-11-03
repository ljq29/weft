from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from weft.engine import Engine
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument, validate_workflow
from weft.workflow.metanodes import expand_metanodes


def node(node_id: str, node_type: str, params: dict) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "node_version": 1,
        "name": node_type,
        "position": {"x": 0, "y": 0},
        "params": params,
    }


def workflow(nodes: list[dict], edges: list[dict]) -> WorkflowDocument:
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "meta-test",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": nodes,
            "edges": edges,
        }
    )


def edge(edge_id: str, source: str, source_port: str, target: str, target_port: str) -> dict:
    return {
        "id": edge_id,
        "source": source,
        "sourcePort": source_port,
        "target": target,
        "targetPort": target_port,
        "order": 0,
    }


@pytest.mark.integration
def test_metanode_inline_execution_and_frozen_source(tmp_path: Path) -> None:
    """US-DES-09/AC-1,3: inlined sub-graph has the same downstream result as flat nodes."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "input.csv").write_text("value\n1\n2\n3\n", encoding="utf-8")
    read = node("n_00000002", "table.read_csv", {"path": "data/input.csv"})
    filtered = node(
        "n_00000003",
        "table.row_filter",
        {"column": "value", "operator": ">", "value": "1"},
    )
    count = node("n_00000004", "table.row_count", {})
    internal_edge = edge("e_00000001", read["id"], "out", filtered["id"], "in")
    external_edge = edge("e_00000002", filtered["id"], "out", count["id"], "in")
    flat = workflow(
        [node("n_00000001", "flow.trigger", {}), read, filtered, count],
        [internal_edge, external_edge],
    )

    async def scenario() -> None:
        engine = Engine()
        registry = builtin_registry()
        flat_record = await engine.run(engine.prepare(flat, tmp_path, registry))
        assert flat_record.nodes[count["id"]].outputs["variables"].inline == {"row_count": 2}
        meta = node(
            "n_00000005",
            "flow.metanode",
            {
                "graph": {"nodes": [read, filtered], "edges": [internal_edge]},
                "interface": {
                    "inputs": {},
                    "outputs": {"out": {"node": filtered["id"], "port": "out"}},
                },
            },
        )
        folded = workflow(
            [node("n_00000001", "flow.trigger", {}), meta, count],
            [edge("e_00000002", meta["id"], "out", count["id"], "in")],
        )
        report = validate_workflow(folded, registry.declarations_for(folded))
        assert not report.errors
        expanded = expand_metanodes(folded)
        assert "meta_n_00000005/n_00000003" in {item.id for item in expanded.nodes}
        outgoing = next(item for item in expanded.edges if item.target == count["id"])
        assert outgoing.source == "meta_n_00000005/n_00000003"
        prepared = engine.prepare(folded, tmp_path, registry)
        folded_record = await engine.run(prepared)
        assert folded_record.status == "succeeded"
        assert folded_record.nodes[count["id"]].outputs["variables"].inline == {"row_count": 2}
        frozen_path = prepared.record.to_dict()["frozen_workflow"]
        frozen = json.loads((tmp_path / frozen_path).read_text(encoding="utf-8"))
        assert frozen["nodes"][1]["type"] == "flow.metanode"
        assert frozen["nodes"][1]["params"]["graph"]["nodes"][0]["id"] == read["id"]

    asyncio.run(scenario())
