from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import polars as pl
from weft_sdk import ToolCapability

from weft.agent.templates import markdown_table


class NodeTool:
    def __init__(
        self,
        prepared: Any,
        engine: Any,
        descriptor: dict[str, Any],
        agent_node: str,
    ) -> None:
        self.prepared = prepared
        self.engine = engine
        self.descriptor = descriptor
        self.agent_node = agent_node
        self.name = descriptor["name"]
        self.description = descriptor["description"]
        self.target_id = descriptor["binding"]["target_node"]
        self.exposed_params = list(descriptor.get("exposed_params", []))
        self.result_format = descriptor.get("result_format", "json")
        self.lane = "trusted"
        self.requires_confirmation = bool(descriptor.get("requires_confirmation", False))
        self.tool_timeout = float(descriptor.get("tool_timeout", 120))
        self.target = self._validate()

    def _validate(self) -> Any:
        target = next(
            (node for node in self.prepared.workflow.nodes if node.id == self.target_id), None
        )
        if target is None:
            raise ValueError(f"NodeTool target '{self.target_id}' not found")
        declaration = self.prepared.registry.get(target.type)
        capability = declaration.tool_capability
        if (
            capability == ToolCapability.NONE
            or target.type.startswith(("agent.", "code.", "user."))
            or target.type == "shell.command"
        ):
            raise PermissionError(f"Node '{target.type}' is not an authorized tool")
        allowed = set(declaration.tool_exposed_params)
        if not set(self.exposed_params) <= allowed:
            raise PermissionError("NodeTool exposed_params exceed the target whitelist")
        if capability == ToolCapability.SIDE_EFFECT:
            if not self.descriptor.get("allow_side_effects"):
                raise PermissionError("Side-effect tools require explicit designer authorization")
            if not self.descriptor.get("require_confirmation", True):
                raise PermissionError("Side-effect tools require confirmation on every call")
            self.requires_confirmation = True
        predecessors: dict[str, set[str]] = {}
        for node in self.prepared.workflow.nodes:
            predecessors[node.id] = set()
        for edge in self.prepared.workflow.edges:
            predecessors[edge.target].add(edge.source)
        pending = list(predecessors[self.target_id])
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == self.agent_node:
                raise ValueError("NodeTool cannot target itself or its ancestors")
            if current not in visited:
                visited.add(current)
                pending.extend(predecessors[current])
        return target

    @property
    def parameters(self) -> dict[str, Any]:
        original = self.prepared.registry.get(self.target.type).params_schema
        properties = original.get("properties", {})
        return {
            "type": "object",
            "properties": {name: properties[name] for name in self.exposed_params},
            "required": [
                name for name in original.get("required", []) if name in self.exposed_params
            ],
            "additionalProperties": False,
        }

    def invoke(self, args: dict[str, Any]) -> str:
        import asyncio

        return asyncio.run(self._invoke(args))

    async def _invoke(self, args: dict[str, Any]) -> str:
        self._validate()
        if self.requires_confirmation:
            if self.engine.confirmation_handler is None:
                raise PermissionError("Tool call requires confirmation")
            approved = await self.engine.confirmation_handler(
                {
                    "run_id": self.prepared.record.run_id,
                    "node_id": self.agent_node,
                    "tool": self.name,
                    "args": args,
                }
            )
            if approved is not True:
                raise PermissionError("Tool call was rejected")
        params = dict(self.target.params)
        params.update(args)
        inputs = self.engine._tool_inputs(self.prepared, self.target_id)
        outputs = await self.engine.execute_single(
            self.prepared,
            self.target_id,
            params,
            inputs,
            timeout=self.tool_timeout,
        )
        if not outputs:
            return ""
        port = self.prepared.registry.get(self.target.type).outputs[0].name
        value = outputs[port]
        if isinstance(value, pl.DataFrame):
            if self.result_format == "table_markdown":
                return markdown_table(value, 50)
            value = value.to_dicts()
        if self.result_format == "text":
            return str(value)
        return json.dumps(value, ensure_ascii=False, default=str)


def validate_node_tools(document: Any, registry: Any) -> None:
    class ValidatorEngine:
        confirmation_handler = None

    prepared = SimpleNamespace(workflow=document, registry=registry)

    for node in document.nodes:
        if node.type != "agent.node_tool":
            continue
        params = node.params
        descriptor = {
            "name": params.get("tool_name", ""),
            "description": params.get("description", ""),
            "binding": {"target_node": params.get("target_node", "")},
            "exposed_params": params.get("exposed_params", []),
            "allow_side_effects": params.get("allow_side_effects", False),
            "require_confirmation": params.get("require_confirmation", True),
        }
        NodeTool(prepared, ValidatorEngine(), descriptor, node.id)
