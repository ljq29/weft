from __future__ import annotations

from pathlib import Path

import pytest
import weft_sdk as weft
from weft_sdk import CachePolicy, DynamicPortGroup, Node, Port, ToolCapability, weft_ctx


@weft.node
class ExampleNode(Node):
    type = "user.example"
    version = 1
    category = "user"
    description = "Example custom node"
    inputs = (Port("in", "table", "Input table"),)
    outputs = (Port("out", "table", "Output table"),)
    dynamic_inputs = (DynamicPortGroup("extra_", "table", min_ports=2),)
    cache_policy = CachePolicy.PURE
    tool_capability = ToolCapability.READ_ONLY
    tool_exposed_params = ["value"]
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"value": {"type": "string", "description": "Example value"}},
    }

    def execute(self, ctx: object, inputs: dict, params: dict) -> dict:
        return {"out": inputs["in"]}


def test_custom_node_decorator_and_dynamic_manifest() -> None:
    """T1.3: custom nodes register declarations and instantiate named dynamic ports."""
    node = ExampleNode()
    assert node.__weft_node__ is True
    manifest = node.manifest({"input_count": 3})
    assert [port["name"] for port in manifest["inputs"]] == ["in", "extra_1", "extra_2", "extra_3"]
    assert manifest["cache_policy"] == "pure"
    assert manifest["tool_exposed_params"] == ["value"]


def test_dynamic_ports_enforce_minimum() -> None:
    """T1.3: dynamic groups reject fewer than their declared minimum ports."""
    with pytest.raises(ValueError, match="at least 2"):
        ExampleNode().manifest({"input_count": 1})


def test_weft_context_root_vars_logging_progress_and_cancellation(tmp_path: Path) -> None:
    """T1.3: weft_ctx exposes the minimal trusted worker API."""
    events: list[tuple[str, object]] = []
    with weft_ctx.activate(
        root=tmp_path,
        run_id="r_test",
        variables={"x": 1},
        log=lambda level, message: events.append((level, message)),
        progress=lambda fraction, message: events.append(("progress", fraction)),
    ):
        assert weft_ctx.root == tmp_path
        assert weft_ctx.run_id == "r_test"
        assert weft_ctx.vars["x"] == 1
        assert weft_ctx.resolve("data/a.csv") == tmp_path / "data/a.csv"
        weft_ctx.log("hello")
        weft_ctx.progress(0.5)
        weft_ctx.check_cancelled()
    assert events == [("INFO", "hello"), ("progress", 0.5)]


def test_weft_context_cancellation(tmp_path: Path) -> None:
    """T1.3: cooperative cancellation raises the public Cancelled exception."""
    with weft_ctx.activate(root=tmp_path, run_id="r_test", cancelled=lambda: True):
        with pytest.raises(weft_ctx.Cancelled):
            weft_ctx.check_cancelled()
