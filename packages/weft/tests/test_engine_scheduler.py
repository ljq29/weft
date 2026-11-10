from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest
from weft.engine import Engine, RunCoordinator, RunQueueFullError, UnconfiguredNodesError
from weft.nodes.flow import TriggerNode
from weft.nodes.registry import NodeRegistry
from weft.workflow import WorkflowDocument
from weft_sdk import Node, Port


class TimedNode(Node):
    type = "user.timed"
    category = "user"
    description = "Synthetic timed node"
    inputs = (Port("flow", "flow", "Ordering input"), Port("variables", "variable", "Variables"))
    outputs = (Port("out", "variable", "Result"),)
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "delay": {"type": "number", "description": "Delay"},
            "value": {"type": "integer", "description": "Value"},
        },
        "required": ["value"],
    }
    intervals: list[tuple[float, float]] = []
    lock = threading.Lock()

    def execute(self, ctx: object, inputs: dict, params: dict) -> dict:
        started = time.perf_counter()
        deadline = time.monotonic() + params.get("delay", 0)
        while time.monotonic() < deadline:
            ctx.check_cancelled()
            time.sleep(min(0.01, deadline - time.monotonic()))
        with self.lock:
            self.intervals.append((started, time.perf_counter()))
        return {"out": {"value": params["value"]}}


class BranchNode(Node):
    type = "user.branch"
    category = "user"
    description = "Synthetic branch"
    outputs = (Port("true", "flow", "True"), Port("false", "flow", "False"))
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"value": {"type": "integer", "description": "Branch value"}},
        "required": ["value"],
    }

    def execute(self, ctx: object, inputs: dict, params: dict) -> dict:
        return {"activated_ports": ["true" if params["value"] else "false"]}


class MergeNode(Node):
    type = "flow.merge"
    category = "flow"
    description = "Synthetic merge"
    inputs = (Port("left", "flow", "Left"), Port("right", "flow", "Right"))
    outputs = (Port("out", "variable", "Merged"),)

    def execute(self, ctx: object, inputs: dict, params: dict) -> dict:
        return {"out": {"merged": True}}


def registry() -> NodeRegistry:
    result = NodeRegistry()
    for node in (TriggerNode, TimedNode, BranchNode, MergeNode):
        result.register(node)
    return result


def node(node_id: str, node_type: str, value: int = 1) -> dict:
    params = {"value": value}
    if node_type == "user.timed":
        params["delay"] = 0.08
    return {
        "id": node_id,
        "type": node_type,
        "node_version": 1,
        "name": node_id,
        "position": {"x": 0, "y": 0},
        "params": params,
    }


def workflow(
    nodes: list[dict], edges: list[dict] | None = None, policy: str = "queue"
) -> WorkflowDocument:
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "engine-test",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "settings": {"concurrency_policy": policy},
            "nodes": nodes,
            "edges": edges or [],
        }
    )


def edge(
    edge_id: str, source: str, source_port: str, target: str, target_port: str = "flow"
) -> dict:
    return {
        "id": edge_id,
        "source": source,
        "sourcePort": source_port,
        "target": target,
        "targetPort": target_port,
        "order": 0,
    }


def test_independent_branches_execute_in_parallel(tmp_path: Path) -> None:
    """US-EXE-01/AC-2: independent synthetic nodes overlap in actual execution time."""

    async def valid_scenario() -> None:
        TimedNode.intervals = []
        engine = Engine()
        document = workflow(
            [
                node("n_00000001", "flow.trigger"),
                node("n_00000002", "user.timed"),
                node("n_00000003", "user.timed"),
            ]
        )
        record = await engine.run(engine.prepare(document, tmp_path, registry()))
        assert record.status == "succeeded"
        assert max(start for start, _ in TimedNode.intervals) < min(
            end for _, end in TimedNode.intervals
        )

    asyncio.run(valid_scenario())


def test_unconfigured_nodes_reject_run(tmp_path: Path) -> None:
    """US-EXE-01/AC-3: missing required params prevent the whole run."""
    engine = Engine()
    document = workflow([node("n_00000001", "flow.trigger"), node("n_00000002", "user.timed")])
    document.nodes[1].params = {"delay": 0}
    with pytest.raises(UnconfiguredNodesError):
        engine.prepare(document, tmp_path, registry())


def test_run_freezes_graph_params_manifest_and_outputs(tmp_path: Path) -> None:
    """US-EXE-04/AC-6, US-EXE-04/AC-7: frozen inputs and immutable outputs."""

    async def scenario() -> None:
        engine = Engine()
        document = workflow(
            [node("n_00000001", "flow.trigger"), node("n_00000002", "user.timed", 7)]
        )
        prepared = engine.prepare(document, tmp_path, registry())
        document.nodes[1].params["value"] = 99
        record = await engine.run(prepared)
        frozen = json.loads(
            (tmp_path / ".runs" / record.run_id / "workflow.json").read_text(encoding="utf-8")
        )
        assert frozen["nodes"][1]["params"]["value"] == 7
        assert frozen["node_manifest"][1]["type"] == "user.timed"
        assert record.nodes["n_00000002"].outputs["out"].inline == {"value": 7}
        meta = json.loads(
            (tmp_path / ".runs" / record.run_id / "meta.json").read_text(encoding="utf-8")
        )
        assert meta["nodes"]["n_00000002"]["outputs"]["out"]["inline"] == {"value": 7}

    asyncio.run(scenario())


def test_finished_event_contains_immutable_output_references(tmp_path: Path) -> None:
    """US-EXE-05/AC-6: the current Run receives previewable output references immediately."""
    engine = Engine()
    events: list[dict] = []
    engine.event_sink = events.append
    document = workflow([node("n_00000001", "flow.trigger"), node("n_00000002", "user.timed", 7)])

    record = asyncio.run(engine.run(engine.prepare(document, tmp_path, registry())))

    assert record.status == "succeeded"
    finished = next(
        event
        for event in events
        if event["event"] == "node.finished" and event["node_id"] == "n_00000002"
    )
    assert finished["data"]["from_cache"] is False
    assert finished["data"]["outputs"]["out"]["kind"] == "json"
    assert finished["data"]["outputs"]["out"]["inline"] == {"value": 7}


def test_branch_skip_and_merge_reach_terminal_states(tmp_path: Path) -> None:
    """T1.4: inactive branches skip while Merge executes once with one successful input."""

    async def scenario() -> None:
        engine = Engine()
        document = workflow(
            [
                node("n_00000001", "flow.trigger"),
                node("n_00000002", "user.branch", 1),
                node("n_00000003", "user.timed"),
                node("n_00000004", "user.timed"),
                node("n_00000005", "flow.merge"),
            ],
            [
                edge("e_00000001", "n_00000002", "true", "n_00000003"),
                edge("e_00000002", "n_00000002", "false", "n_00000004"),
                edge("e_00000003", "n_00000003", "out", "n_00000005", "left"),
                edge("e_00000004", "n_00000004", "out", "n_00000005", "right"),
            ],
        )
        record = await engine.run(engine.prepare(document, tmp_path, registry()))
        assert record.status == "succeeded"
        assert record.nodes["n_00000003"].status == "executed"
        assert record.nodes["n_00000004"].status == "skipped_branch"
        assert record.nodes["n_00000005"].status == "executed"

    asyncio.run(scenario())


def test_queue_drop_and_queue_limit(tmp_path: Path) -> None:
    """US-EXE-13/AC-1, US-EXE-13/AC-2: queue, drop and the ten-item queue bound are enforced."""

    async def scenario() -> None:
        engine = Engine()
        coordinator = RunCoordinator(engine, queue_limit=2)
        document = workflow([node("n_00000001", "flow.trigger"), node("n_00000002", "user.timed")])
        first = await coordinator.submit(document, tmp_path, registry())
        second = await coordinator.submit(document, tmp_path, registry())
        third = await coordinator.submit(document, tmp_path, registry())
        assert first.disposition == "started"
        assert second.disposition == third.disposition == "queued"
        with pytest.raises(RunQueueFullError):
            await coordinator.submit(document, tmp_path, registry())
        for run_id in (first.run_id, second.run_id, third.run_id):
            assert run_id is not None
            await coordinator.wait(run_id)
        dropped = workflow([node("n_00000001", "flow.trigger")], policy="drop")
        await coordinator.submit(dropped, tmp_path, registry())
        result = await coordinator.submit(dropped, tmp_path, registry())
        assert result.disposition == "dropped"
        assert result.run_id is None

    asyncio.run(scenario())


def test_cancel_previous_starts_new_run_after_cancellation(tmp_path: Path) -> None:
    """US-EXE-13/AC-1: cancel_previous cancels the active run before the queued run starts."""

    async def scenario() -> None:
        engine = Engine()
        coordinator = RunCoordinator(engine)
        document = workflow(
            [node("n_00000001", "flow.trigger"), node("n_00000002", "user.timed")],
            policy="cancel_previous",
        )
        document.nodes[1].params["delay"] = 0.5
        first = await coordinator.submit(document, tmp_path, registry())
        second = await coordinator.submit(document, tmp_path, registry())
        assert second.disposition == "queued"
        assert first.run_id is not None and second.run_id is not None
        await coordinator.wait(first.run_id)
        await coordinator.wait(second.run_id)
        assert engine.runs[first.run_id].record.status == "cancelled"
        assert engine.runs[second.run_id].record.status == "succeeded"

    asyncio.run(scenario())


def test_run_meta_is_replaced_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """US-EXE-04/AC-6: Run metadata readers never observe a partial JSON write."""
    engine = Engine()
    prepared = engine.prepare(workflow([node("n_00000001", "flow.trigger")]), tmp_path, registry())
    original_replace = Path.replace
    replacements: list[tuple[Path, Path]] = []

    def track_replace(source: Path, target: Path) -> Path:
        replacements.append((source, target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", track_replace)
    engine._write_meta(prepared)

    path = tmp_path / ".runs" / prepared.record.run_id / "meta.json"
    assert replacements == [(path.with_suffix(".tmp"), path)]
    assert not path.with_suffix(".tmp").exists()
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == prepared.record.run_id
