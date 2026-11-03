from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pyarrow as pa
import pytest
from weft.engine import Engine, UnconfiguredNodesError
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument


def node(node_id: str, node_type: str, params: dict) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "node_version": 1,
        "name": node_type,
        "position": {"x": 0, "y": 0},
        "params": params,
    }


def edge(edge_id: str, source: str, source_port: str, target: str, target_port: str) -> dict:
    return {
        "id": edge_id,
        "source": source,
        "sourcePort": source_port,
        "target": target,
        "targetPort": target_port,
        "order": 0,
    }


def workflow(nodes: list[dict], edges: list[dict]) -> WorkflowDocument:
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "loops",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": nodes,
            "edges": edges,
        }
    )


def read_output(root: Path, record: object, node_id: str) -> list[dict]:
    reference = record.nodes[node_id].outputs["out"]
    path = root / reference.path
    with pa.memory_map(str(path)) as source:
        return pa.ipc.open_file(source).read_all().to_pylist()


def test_row_loop_concatenates_body_tables_and_reports_iterations(tmp_path: Path) -> None:
    """US-EXE-10/AC-1,3,4: row loops execute each iteration and concatenate outputs."""

    async def scenario() -> None:
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "input.csv").write_text("amount\n1\n2\n3\n", encoding="utf-8")
        document = workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node("n_00000002", "table.read_csv", {"path": "data/input.csv"}),
                node("n_00000003", "flow.loop_start", {"mode": "row", "loop_id": "rows"}),
                node(
                    "n_00000004",
                    "table.row_filter",
                    {"column": "amount", "operator": ">", "value": "1"},
                ),
                node("n_00000005", "flow.loop_end", {"loop_id": "rows", "mode": "concat"}),
                node("n_00000006", "table.write_csv", {"path": "out/result.csv"}),
            ],
            [
                edge("e_00000001", "n_00000002", "out", "n_00000003", "in"),
                edge("e_00000002", "n_00000003", "table", "n_00000004", "in"),
                edge("e_00000003", "n_00000004", "out", "n_00000005", "in"),
                edge("e_00000004", "n_00000005", "out", "n_00000006", "in"),
            ],
        )
        engine = Engine()
        record = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert record.status == "succeeded"
        assert read_output(tmp_path, record, "n_00000005") == [{"amount": 2}, {"amount": 3}]
        events = [
            json.loads(line)
            for line in (tmp_path / ".runs" / record.run_id / "log.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        iterations = [event for event in events if event["event"] == "node.iteration"]
        assert [event["data"]["index"] for event in iterations] == [1, 2, 3]
        cache_keys = [
            json.loads(path.read_text(encoding="utf-8"))["key"]
            for path in (tmp_path / ".runs" / "cache" / "n_00000004").glob("meta.json")
        ]
        assert len(cache_keys) == 1

    asyncio.run(scenario())


def test_chunk_counting_and_variables_collection(tmp_path: Path) -> None:
    """US-EXE-11/AC-1,2,3: chunking, half-open counting and variable collection work."""

    async def scenario() -> None:
        document = workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node(
                    "n_00000002",
                    "flow.loop_start",
                    {"mode": "counting", "loop_id": "count", "from": 0, "to": 5, "step": 1},
                ),
                node(
                    "n_00000003",
                    "flow.variable",
                    {"values": [{"name": "value", "type": "int", "value": 1}]},
                ),
                node("n_00000004", "flow.loop_end", {"loop_id": "count", "mode": "variables"}),
            ],
            [edge("e_00000001", "n_00000002", "variables", "n_00000003", "variables")],
        )
        engine = Engine()
        record = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert record.status == "succeeded"
        assert len(read_output(tmp_path, record, "n_00000004")) == 5
        invalid = workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node(
                    "n_00000002",
                    "flow.loop_start",
                    {"mode": "counting", "loop_id": "bad", "from": 0, "to": 1, "step": 0},
                ),
            ],
            [],
        )
        with pytest.raises(UnconfiguredNodesError, match="Loop Start"):
            engine.prepare(invalid, tmp_path, builtin_registry())

    asyncio.run(scenario())


def test_loop_skip_error_adds_error_rows(tmp_path: Path) -> None:
    """US-EXE-10/AC-2: on_error=skip records an _error row instead of failing the run."""

    async def scenario() -> None:
        document = workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node(
                    "n_00000002",
                    "flow.loop_start",
                    {"mode": "counting", "loop_id": "skip", "from": 0, "to": 2, "step": 1},
                ),
                node(
                    "n_00000003",
                    "table.row_filter",
                    {"column": "missing", "operator": ">", "value": "1"},
                ),
                node(
                    "n_00000004",
                    "flow.loop_end",
                    {"loop_id": "skip", "mode": "concat", "on_error": "skip"},
                ),
            ],
            [edge("e_00000001", "n_00000002", "table", "n_00000003", "in")],
        )
        engine = Engine()
        record = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert record.status == "succeeded"
        assert read_output(tmp_path, record, "n_00000004") == [
            {"_error": "failed"},
            {"_error": "failed"},
        ]

    asyncio.run(scenario())


def test_chunk_and_negative_step(tmp_path: Path) -> None:
    """US-EXE-11/AC-1,2: chunks contain fixed-size rows and negative steps use half-open ranges."""

    async def scenario() -> None:
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "input.csv").write_text("amount\n1\n2\n3\n4\n5\n", encoding="utf-8")
        document = workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node("n_00000002", "table.read_csv", {"path": "data/input.csv"}),
                node(
                    "n_00000003",
                    "flow.loop_start",
                    {"mode": "chunk", "loop_id": "chunk", "chunk_size": 2},
                ),
                node(
                    "n_00000004",
                    "table.row_filter",
                    {"column": "amount", "operator": ">", "value": "0"},
                ),
                node("n_00000005", "flow.loop_end", {"loop_id": "chunk", "mode": "concat"}),
            ],
            [
                edge("e_00000001", "n_00000002", "out", "n_00000003", "in"),
                edge("e_00000002", "n_00000003", "table", "n_00000004", "in"),
                edge("e_00000003", "n_00000004", "out", "n_00000005", "in"),
            ],
        )
        engine = Engine()
        record = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert record.status == "succeeded"
        assert len(read_output(tmp_path, record, "n_00000005")) == 5
        iterations = [
            json.loads(line)
            for line in (tmp_path / ".runs" / record.run_id / "log.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if json.loads(line)["event"] == "node.iteration"
        ]
        assert len(iterations) == 3
        from weft.engine.loops import iterations as make_iterations

        start = next(item for item in document.nodes if item.type == "flow.loop_start")
        start.params.update({"mode": "counting", "from": 3, "to": 0, "step": -1})
        assert [vars["i"] for _, vars in make_iterations(None, start, {})] == [3, 2, 1]

    asyncio.run(scenario())
