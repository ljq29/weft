from __future__ import annotations

from pathlib import Path

import pytest
from weft.nodes.registry import builtin_registry
from weft.workflow.demos import create_demo, list_demos
from weft.workflow.store import WorkflowStore
from weft.workflow.validation import validate_workflow


@pytest.mark.parametrize("demo_id", [demo.id for demo in list_demos()])
def test_builtin_demo_graph_is_valid_and_reachable_from_trigger(
    demo_id: str, tmp_path: Path
) -> None:
    """US-DES-01/AC-4: every demo node is reachable from Trigger in a valid graph."""
    root = create_demo(demo_id, f"{demo_id}-graph", tmp_path)
    document = WorkflowStore(root).load()
    registry = builtin_registry()

    edge_ids = [edge.id for edge in document.edges]
    assert len(edge_ids) == len(set(edge_ids))
    assert validate_workflow(document, registry.declarations_for(document)).errors == ()

    trigger = next(node for node in document.nodes if node.type == "flow.trigger")
    reachable = {trigger.id}
    pending = [trigger.id]
    while pending:
        source = pending.pop()
        for edge in document.edges:
            if edge.source == source and edge.target not in reachable:
                reachable.add(edge.target)
                pending.append(edge.target)

    business_nodes = {node.id for node in document.nodes if node.type != "flow.trigger"}
    assert business_nodes <= reachable
