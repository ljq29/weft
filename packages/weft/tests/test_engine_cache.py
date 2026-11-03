from __future__ import annotations

import asyncio
import json
from pathlib import Path

from weft.engine import Engine
from weft.engine.cache import CacheManager
from weft.nodes.flow import TriggerNode
from weft.nodes.registry import NodeRegistry
from weft.workflow import WorkflowDocument
from weft.workflow.values import ValueRef
from weft_sdk import CachePolicy, Node, Port


class CountingNode(Node):
    type = "user.pure"
    category = "user"
    description = "Pure counting node"
    cache_policy = CachePolicy.PURE
    outputs = (Port("out", "variable", "Result"),)
    calls = 0
    large = False

    def execute(self, ctx: object, inputs: dict, params: dict) -> dict:
        type(self).calls += 1
        value = "x" * 300_000 if self.large else params.get("value", 1)
        return {"out": {"value": value}}


class VolatileNode(CountingNode):
    type = "user.volatile"
    cache_policy = CachePolicy.VOLATILE
    calls = 0


class SideEffectNode(CountingNode):
    type = "user.side_effect"
    cache_policy = CachePolicy.SIDE_EFFECT
    calls = 0


class BranchNode(Node):
    type = "user.cached_branch"
    category = "user"
    description = "Cached branch"
    cache_policy = CachePolicy.PURE
    outputs = (Port("true", "flow", "True"), Port("false", "flow", "False"))
    calls = 0

    def execute(self, ctx: object, inputs: dict, params: dict) -> dict:
        type(self).calls += 1
        return {"activated_ports": ["false"]}


def registry() -> NodeRegistry:
    result = NodeRegistry()
    for node in (TriggerNode, CountingNode, VolatileNode, SideEffectNode, BranchNode):
        result.register(node)
    return result


def document(node_type: str) -> WorkflowDocument:
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "cache-test",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": [
                {
                    "id": "n_00000001",
                    "type": "flow.trigger",
                    "node_version": 1,
                    "name": "Trigger",
                    "position": {"x": 0, "y": 0},
                    "params": {},
                },
                {
                    "id": "n_00000002",
                    "type": node_type,
                    "node_version": 1,
                    "name": "Test",
                    "position": {"x": 0, "y": 0},
                    "params": {"value": 1},
                },
            ],
        }
    )


def run_twice(node_type: str, tmp_path: Path) -> tuple[object, object]:
    async def scenario() -> tuple[object, object]:
        engine = Engine()
        first = await engine.run(engine.prepare(document(node_type), tmp_path, registry()))
        second = await engine.run(engine.prepare(document(node_type), tmp_path, registry()))
        return first, second

    return asyncio.run(scenario())


def test_cache_policy_classification_and_pure_reuse(tmp_path: Path) -> None:
    """US-EXE-04/AC-1: pure nodes reuse while volatile and side-effect nodes always execute."""
    CountingNode.calls = VolatileNode.calls = SideEffectNode.calls = 0
    first, second = run_twice("user.pure", tmp_path)
    assert second.nodes["n_00000002"].from_cache is True
    assert CountingNode.calls == 1
    run_twice("user.volatile", tmp_path / "volatile")
    run_twice("user.side_effect", tmp_path / "side")
    assert VolatileNode.calls == 2
    assert SideEffectNode.calls == 2
    assert Node.cache_policy == CachePolicy.SIDE_EFFECT


def test_corrupt_cache_is_a_miss(tmp_path: Path) -> None:
    """US-EXE-04/AC-5: corrupted cache metadata cannot suppress execution."""
    CountingNode.calls = 0
    first, second = run_twice("user.pure", tmp_path)
    meta = tmp_path / ".runs" / "cache" / "n_00000002" / "meta.json"
    meta.write_text("not json", encoding="utf-8")
    CountingNode.calls = 0

    async def scenario() -> None:
        engine = Engine()
        record = await engine.run(engine.prepare(document("user.pure"), tmp_path, registry()))
        assert record.nodes["n_00000002"].from_cache is False

    asyncio.run(scenario())
    assert CountingNode.calls == 1


def test_cached_large_output_is_materialized_and_survives_reset(tmp_path: Path) -> None:
    """US-EXE-04/AC-5: cache hits copy immutable run outputs which survive cache reset."""
    CountingNode.large = True
    first, second = run_twice("user.pure", tmp_path)
    assert second.nodes["n_00000002"].from_cache is True
    reference = second.nodes["n_00000002"].outputs["out"]
    assert reference.path is not None
    snapshot = tmp_path / reference.path
    assert snapshot.is_file()
    CacheManager(tmp_path).reset("n_00000002")
    assert snapshot.is_file()
    assert json.loads(snapshot.read_text(encoding="utf-8"))["value"] == "x" * 300_000
    CountingNode.large = False


def test_branch_decision_is_replayed_from_cache(tmp_path: Path) -> None:
    """US-EXE-04/AC-5: activated_ports are restored with cached outputs."""
    BranchNode.calls = 0
    first, second = run_twice("user.cached_branch", tmp_path)
    assert second.nodes["n_00000002"].from_cache is True
    assert second.nodes["n_00000002"].activated_ports == ["false"]
    assert BranchNode.calls == 1


def test_cache_lru_removes_oldest_entry(tmp_path: Path) -> None:
    """T1.5: LRU cleanup removes old cache entries without touching run snapshots."""
    manager = CacheManager(tmp_path)
    value = ValueRef.from_json({"value": 1})
    manager.store("n_00000001", "old", {"out": value}, None)
    manager.store("n_00000002", "new", {"out": value}, None)
    manager.touch("n_00000002")
    newest = tmp_path / ".runs" / "cache" / "n_00000002"
    newest_size = sum(path.stat().st_size for path in newest.rglob("*") if path.is_file())
    manager.enforce_lru(newest_size)
    assert not (tmp_path / ".runs" / "cache" / "n_00000001").exists()
    assert (tmp_path / ".runs" / "cache" / "n_00000002").exists()
