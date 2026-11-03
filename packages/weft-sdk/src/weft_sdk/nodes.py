from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar


class Lane(StrEnum):
    TRUSTED_WORKER = "trusted_worker"
    TRUSTED_SERVICE = "trusted_service"
    SANDBOXED = "sandboxed"


class CachePolicy(StrEnum):
    PURE = "pure"
    VOLATILE = "volatile"
    SIDE_EFFECT = "side_effect"


class ToolCapability(StrEnum):
    NONE = "none"
    READ_ONLY = "read_only"
    SIDE_EFFECT = "side_effect"


@dataclass(frozen=True)
class Port:
    name: str
    kind: str
    description: str


@dataclass(frozen=True)
class DynamicPortGroup:
    prefix: str
    kind: str
    min_ports: int = 2
    count_param: str = "input_count"

    def instantiate(self, params: dict[str, Any]) -> tuple[Port, ...]:
        count = params.get(self.count_param, self.min_ports)
        if not isinstance(count, int) or count < self.min_ports:
            raise ValueError(f"{self.count_param} must instantiate at least {self.min_ports} ports")
        return tuple(
            Port(f"{self.prefix}{index}", self.kind, f"Dynamic input {index}")
            for index in range(1, count + 1)
        )


@dataclass(frozen=True)
class ExternalInput:
    name: str
    kind: str


@dataclass(frozen=True)
class ExternalResource:
    param: str
    kind: str


class Node:
    __weft_node__: ClassVar[bool] = False
    type: ClassVar[str]
    version: ClassVar[int] = 1
    category: ClassVar[str]
    name: ClassVar[str] = ""
    description: ClassVar[str]
    lane: ClassVar[Lane] = Lane.TRUSTED_WORKER
    cache_policy: ClassVar[CachePolicy] = CachePolicy.SIDE_EFFECT
    tool_capability: ClassVar[ToolCapability] = ToolCapability.NONE
    inputs: ClassVar[tuple[Port, ...]] = ()
    outputs: ClassVar[tuple[Port, ...]] = ()
    dynamic_inputs: ClassVar[tuple[DynamicPortGroup, ...]] = ()
    params_schema: ClassVar[dict[str, Any]] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {},
    }
    ui_hints: ClassVar[dict[str, Any]] = {}
    tool_exposed_params: ClassVar[list[str]] = []
    portable_params: ClassVar[list[str]] = []
    external_resources: ClassVar[list[ExternalResource]] = []
    cache_inputs: ClassVar[list[ExternalInput]] = []

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def instantiated_inputs(self, params: dict[str, Any]) -> tuple[Port, ...]:
        return self.inputs + tuple(
            port for group in self.dynamic_inputs for port in group.instantiate(params)
        )

    def instantiated_outputs(self, params: dict[str, Any]) -> tuple[Port, ...]:
        return self.outputs

    def manifest(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": self.type,
            "node_version": self.version,
            "category": self.category,
            "name": self.name or self.type,
            "description": self.description,
            "lane": self.lane.value,
            "cache_policy": self.cache_policy.value,
            "tool_capability": self.tool_capability.value,
            "inputs": [port.__dict__ for port in self.instantiated_inputs(params)],
            "outputs": [port.__dict__ for port in self.instantiated_outputs(params)],
            "params_schema": self.params_schema,
            "ui_hints": self.ui_hints,
            "tool_exposed_params": list(self.tool_exposed_params),
            "portable_params": list(self.portable_params),
            "external_resources": [resource.__dict__ for resource in self.external_resources],
            "cache_inputs": [item.__dict__ for item in self.cache_inputs],
        }


def node(cls: type[Node]) -> type[Node]:
    if not issubclass(cls, Node) or not cls.type.startswith("user."):
        raise ValueError("Custom nodes must extend Node and use the user.* namespace")
    cls.__weft_node__ = True
    return cls
