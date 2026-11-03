from __future__ import annotations

import asyncio
import os
from pathlib import Path

from weft.engine import Engine
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument


def make_workflow(nodes: list[dict], edges: list[dict]) -> WorkflowDocument:
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "table-cache",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": nodes,
            "edges": edges,
        }
    )


def node(node_id: str, node_type: str, params: dict) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "node_version": 1,
        "name": node_type,
        "position": {"x": 0, "y": 0},
        "params": params,
    }


def edge(edge_id: str, source: str, source_port: str, target: str) -> dict:
    return {
        "id": edge_id,
        "source": source,
        "sourcePort": source_port,
        "target": target,
        "targetPort": "in",
        "order": 0,
    }


def test_file_content_invalidates_read_and_side_effect_write_always_runs(tmp_path: Path) -> None:
    """US-EXE-04/AC-3,4: content SHA-256 invalidates reads while writes always execute."""

    async def scenario() -> None:
        (tmp_path / "data").mkdir()
        source = tmp_path / "data" / "input.csv"
        source.write_text("value\n1\n", encoding="utf-8")
        document = make_workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node("n_00000002", "table.read_csv", {"path": "data/input.csv"}),
                node("n_00000003", "table.write_csv", {"path": "out/result.csv"}),
            ],
            [
                edge("e_00000001", "n_00000002", "out", "n_00000003"),
            ],
        )
        engine = Engine()
        first = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert first.status == "succeeded"
        stat = source.stat()
        source.write_text("value\n2\n", encoding="utf-8")
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        second = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert second.nodes["n_00000002"].from_cache is False
        assert second.nodes["n_00000003"].from_cache is False
        assert (tmp_path / "out" / "result.csv").read_text(encoding="utf-8-sig").splitlines()[
            -1
        ] == "2"

    asyncio.run(scenario())


def test_list_files_directory_fingerprint_invalidates_cache(tmp_path: Path) -> None:
    """US-EXE-04/AC-9: a new matching directory entry invalidates List Files."""

    async def scenario() -> None:
        (tmp_path / "inbox").mkdir()
        (tmp_path / "inbox" / "a.xlsx").write_bytes(b"a")
        document = make_workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node(
                    "n_00000002",
                    "file.list",
                    {"path": "inbox", "pattern": "*.xlsx", "recursive": False},
                ),
            ],
            [],
        )
        engine = Engine()
        await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        (tmp_path / "inbox" / "b.xlsx").write_bytes(b"b")
        second = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert second.nodes["n_00000002"].from_cache is False
        reference = second.nodes["n_00000002"].outputs["out"]
        assert reference.rows == 2

    asyncio.run(scenario())


def test_node_failure_preserves_upstream_and_input_snapshot(tmp_path: Path) -> None:
    """US-EXE-07/AC-1,2: failures stop downstream and retain table input snapshots."""

    async def scenario() -> None:
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "input.csv").write_text("amount\n1\n2\n", encoding="utf-8")
        document = make_workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node("n_00000002", "table.read_csv", {"path": "data/input.csv"}),
                node(
                    "n_00000003",
                    "table.row_filter",
                    {"column": "missing", "operator": ">", "value": "1"},
                ),
                node("n_00000004", "table.write_csv", {"path": "out/result.csv"}),
            ],
            [
                edge("e_00000001", "n_00000002", "out", "n_00000003"),
                edge("e_00000002", "n_00000003", "out", "n_00000004"),
            ],
        )
        engine = Engine()
        record = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert record.status == "failed"
        assert record.nodes["n_00000002"].status == "executed"
        assert record.nodes["n_00000003"].status == "failed"
        assert record.nodes["n_00000004"].status == "skipped_upstream"
        error = record.nodes["n_00000003"].error
        assert error["traceback"]
        assert error["input_snapshot"]["in"] == [{"amount": 1}, {"amount": 2}]

    asyncio.run(scenario())
