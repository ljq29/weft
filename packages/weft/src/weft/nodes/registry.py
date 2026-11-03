from __future__ import annotations

import hashlib
import importlib.util
import inspect
from pathlib import Path
from typing import Any

from weft_sdk import Node

from weft.workflow.ports import PortType
from weft.workflow.validation import NodeDeclaration, PortDeclaration


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}

    def register(self, node_type: type[Node]) -> None:
        node = node_type()
        if node.type in self._nodes:
            raise ValueError(f"Node type '{node.type}' already registered")
        self._nodes[node.type] = node

    def get(self, type_name: str) -> Node:
        try:
            return self._nodes[type_name]
        except KeyError as error:
            raise KeyError(f"Unknown node type: {type_name}") from error

    def all(self) -> tuple[Node, ...]:
        return tuple(self._nodes[key] for key in sorted(self._nodes))

    def declaration(self, type_name: str, params: dict[str, Any] | None = None) -> NodeDeclaration:
        node = self.get(type_name)
        return NodeDeclaration(
            node_type=node.type,
            inputs=[
                PortDeclaration(port.name, PortType(port.kind))
                for port in node.instantiated_inputs(params or {})
            ],
            outputs=[
                PortDeclaration(port.name, PortType(port.kind))
                for port in node.instantiated_outputs(params or {})
            ],
        )

    def declarations(self) -> dict[str, NodeDeclaration]:
        return {node.type: self.declaration(node.type) for node in self.all()}

    def declarations_for(self, workflow: Any) -> dict[str, NodeDeclaration]:
        return {node.type: self.declaration(node.type, node.params) for node in workflow.nodes}

    def load_directory(self, directory: Path) -> None:
        for path in sorted(directory.glob("*.py")):
            spec = importlib.util.spec_from_file_location(f"weft_user_{path.stem}", path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load custom node: {path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for _, value in inspect.getmembers(module, inspect.isclass):
                if (
                    value is not Node
                    and issubclass(value, Node)
                    and value.__dict__.get("__weft_node__", False)
                ):
                    self.register(value)


def implementation_hash(node_type: type[Node]) -> str:
    source = inspect.getsource(node_type).encode("utf-8")
    return f"sha256:{hashlib.sha256(source).hexdigest()}"


def builtin_registry() -> NodeRegistry:
    from weft_worker.builtin import BUILTIN_NODES
    from weft_worker.builtin_extra import BUILTIN_EXTRA_NODES

    from weft.nodes.flow import (
        IfNode,
        LoopEndNode,
        LoopStartNode,
        MergeNode,
        SwitchNode,
        TriggerNode,
        WaitNode,
    )

    registry = NodeRegistry()
    for node_type in (
        TriggerNode,
        IfNode,
        SwitchNode,
        MergeNode,
        WaitNode,
        LoopStartNode,
        LoopEndNode,
    ):
        registry.register(node_type)
    for builtin_type in (*BUILTIN_NODES, *BUILTIN_EXTRA_NODES):
        registry.register(builtin_type)
    return registry
