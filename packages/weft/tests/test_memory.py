from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from weft.agent.memory import MemoryStore
from weft.agent.settings import SettingsStore
from weft.engine import Engine
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


def edge(edge_id: str, source: str, target: str) -> dict:
    return {
        "id": edge_id,
        "source": source,
        "sourcePort": "message",
        "target": target,
        "targetPort": "message",
        "order": 0,
    }


def document(nodes: list[dict], edges: list[dict] | None = None) -> WorkflowDocument:
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "memory",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": nodes,
            "edges": edges or [],
        }
    )


@pytest.mark.integration
def test_memory_save_load_truncate_and_clear_across_runs(tmp_path: Path) -> None:
    """US-AGT-08/AC-1,2: real Runs append, reload and clear session Messages."""
    save = node("n_00000002", "agent.memory_save", {"session_id": "demo"})
    load = node("n_00000004", "agent.memory_load", {"session_id": "demo", "max_messages": 2})

    async def scenario() -> None:
        engine = Engine()
        registry = builtin_registry()
        for text in ("one", "two", "three"):
            prompt = node(
                "n_00000003", "agent.prompt_template", {"template": text, "source": "inline"}
            )
            graph = document(
                [node("n_00000001", "flow.trigger", {}), save, prompt, load],
                [
                    edge("e_00000001", prompt["id"], save["id"]),
                    edge("e_00000002", save["id"], load["id"]),
                ],
            )
            record = await engine.run(engine.prepare(graph, tmp_path, registry))
            assert record.status == "succeeded"
        messages = record.nodes[load["id"]].outputs["message"].inline
        assert [item["content"] for item in messages] == ["two", "three"]
        path = tmp_path / ".runs" / "memory" / "demo.jsonl"
        assert len(path.read_text(encoding="utf-8").splitlines()) == 3
        cleared = await engine.run(
            engine.prepare(
                document(
                    [
                        node("n_00000001", "flow.trigger", {}),
                        node("n_00000005", "agent.memory_clear", {"session_id": "demo"}),
                    ]
                ),
                tmp_path,
                registry,
            )
        )
        assert cleared.status == "succeeded"
        assert MemoryStore(tmp_path).load("demo") == []

    asyncio.run(scenario())


def test_memory_retention_days_and_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """US-AGT-08/AC-3: memory stays under .runs, expires by age, and honors zero."""
    config = tmp_path / "config"
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(config))
    settings = SettingsStore(config / "config.toml")
    store = MemoryStore(tmp_path)
    store.save("demo", [{"role": "user", "content": "old"}])
    path = store.path("demo")
    old = (datetime.now(UTC) - timedelta(days=31)).timestamp()
    os.utime(path, (old, old))
    settings.update({"cache": {"memory_retention_days": 0}})
    assert store.cleanup() == []
    assert path.exists()
    settings.update({"cache": {"memory_retention_days": 30}})
    assert store.cleanup() == [path]
    assert not path.exists()
    with pytest.raises(ValueError):
        store.path("../escape")
