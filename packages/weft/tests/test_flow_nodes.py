from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
import simpleeval
from weft.engine import Engine
from weft.engine.cache import CacheManager
from weft.nodes.flow import IfNode
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument
from weft_sdk import weft_ctx


def make_workflow(nodes: list[dict], edges: list[dict] | None = None) -> WorkflowDocument:
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "flow-test",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "variables": [{"name": "flag", "type": "int", "value": 1}],
            "nodes": nodes,
            "edges": edges or [],
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


def test_if_switch_merge_and_cached_branch_replay(tmp_path: Path) -> None:
    """US-EXE-12/AC-1,2,3,6, US-EXE-04/AC-12: branches merge and replay cached decisions."""

    async def scenario() -> None:
        document = make_workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node("n_00000002", "flow.if", {"condition": "flag == 1"}),
                node("n_00000003", "flow.switch", {"variable": "flag", "cases": {"1": "case_1"}}),
            ]
        )
        engine = Engine()
        first = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        second = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert first.nodes["n_00000002"].activated_ports == ["true"]
        assert first.nodes["n_00000003"].activated_ports == ["case_1"]
        assert second.nodes["n_00000002"].from_cache is True
        assert second.nodes["n_00000002"].activated_ports == ["true"]

    asyncio.run(scenario())


def test_if_expression_rejects_import_and_dunder(tmp_path: Path) -> None:
    """US-EXE-12/AC-4,5: invalid and unsafe expressions fail without executing code."""
    with weft_ctx.activate(root=tmp_path, run_id="r_if", variables={"x": 1}):
        for expression in ("__import__('os')", "x.__class__", "missing > 1"):
            with pytest.raises((simpleeval.InvalidExpression, NameError, AttributeError)):
                IfNode().execute(weft_ctx, {}, {"condition": expression})


def test_wait_normal_duration_and_cancellation(tmp_path: Path) -> None:
    """US-EXE-08/AC-1,4,5: Wait honors duration and cancellation within two seconds."""

    async def normal() -> None:
        engine = Engine()
        document = make_workflow(
            [
                node("n_00000000", "flow.trigger", {}),
                node("n_00000001", "flow.wait", {"duration_seconds": 0.1}),
            ]
        )
        started = time.perf_counter()
        record = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert time.perf_counter() - started >= 0.1
        assert record.status == "succeeded"

    async def cancelled() -> None:
        engine = Engine()
        document = make_workflow(
            [
                node("n_00000000", "flow.trigger", {}),
                node("n_00000001", "flow.wait", {"duration_seconds": 30}),
            ]
        )
        prepared = engine.prepare(document, tmp_path, builtin_registry())
        task = asyncio.create_task(engine.run(prepared))
        await asyncio.sleep(0.05)
        engine.cancel(prepared.record.run_id)
        started = time.perf_counter()
        record = await task
        assert time.perf_counter() - started < 2
        assert record.status == "cancelled"

    asyncio.run(normal())
    asyncio.run(cancelled())


def test_execute_to_from_single_and_reset(tmp_path: Path) -> None:
    """US-EXE-02/AC-1,2, US-EXE-03/AC-1,2,3,4: scopes and cache reset."""

    async def scenario() -> None:
        nodes = [
            node("n_00000001", "flow.trigger", {}),
            node("n_00000002", "flow.if", {"condition": "flag == 1"}),
            node("n_00000003", "flow.if", {"condition": "flag == 1"}),
        ]
        document = make_workflow(nodes)
        engine = Engine()
        scoped = await engine.run(
            engine.prepare(
                document,
                tmp_path,
                builtin_registry(),
                scope={"kind": "to_node", "node_id": "n_00000002"},
            )
        )
        assert scoped.nodes["n_00000003"].status == "out_of_scope"
        single = await engine.run(
            engine.prepare(
                document,
                tmp_path,
                builtin_registry(),
                scope={"kind": "single", "node_id": "n_00000002"},
            )
        )
        assert single.nodes["n_00000002"].from_cache is True
        assert single.nodes["n_00000003"].status == "out_of_scope"
        assert (tmp_path / ".runs" / "cache").exists()
        CacheManager(tmp_path).reset_all()
        assert not (tmp_path / ".runs" / "cache").exists()

    asyncio.run(scenario())


def test_missing_flow_variable_fails_node(tmp_path: Path) -> None:
    """US-DES-06/AC-4: a missing variable fails the consuming node with its name."""

    async def scenario() -> None:
        document = make_workflow(
            [
                node("n_00000001", "flow.trigger", {}),
                node("n_00000002", "flow.if", {"condition": {"$var": "missing"}}),
            ]
        )
        engine = Engine()
        record = await engine.run(engine.prepare(document, tmp_path, builtin_registry()))
        assert record.nodes["n_00000002"].status == "failed"
        assert record.nodes["n_00000002"].error["message"] == "Flow variable 'missing' not found"

    asyncio.run(scenario())
