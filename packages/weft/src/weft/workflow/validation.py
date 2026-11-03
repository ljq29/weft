from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from weft.workflow.models import Edge, Node, WorkflowDocument
from weft.workflow.ports import PortType
from weft.workflow.ports import is_compatible as ports_is_compatible

PortKind = PortType


@dataclass(frozen=True)
class PortDeclaration:
    name: str
    kind: PortKind


@dataclass(frozen=True)
class NodeDeclaration:
    node_type: str
    inputs: tuple[PortDeclaration, ...] = ()
    outputs: tuple[PortDeclaration, ...] = ()
    accepts_partial_inputs: bool = False

    def __init__(
        self,
        node_type: str,
        inputs: list[PortDeclaration] | tuple[PortDeclaration, ...] = (),
        outputs: list[PortDeclaration] | tuple[PortDeclaration, ...] = (),
        accepts_partial_inputs: bool = False,
    ) -> None:
        object.__setattr__(self, "node_type", node_type)
        object.__setattr__(self, "inputs", tuple(inputs))
        object.__setattr__(self, "outputs", tuple(outputs))
        object.__setattr__(self, "accepts_partial_inputs", accepts_partial_inputs)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    node_id: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]


def is_compatible(source: PortKind, target: PortKind) -> bool:
    return ports_is_compatible(source, target)


def _ports(
    node: Node, declarations: Mapping[str, NodeDeclaration]
) -> tuple[dict[str, PortKind], dict[str, PortKind]]:
    declaration = declarations.get(node.type)
    if declaration is None:
        return {}, {}
    return (
        {port.name: port.kind for port in declaration.inputs},
        {port.name: port.kind for port in declaration.outputs},
    )


def _absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _walk_params(value: Any, path: str = "") -> Iterator[tuple[str, str, str]]:
    if isinstance(value, dict):
        if set(value) == {"$var"} and isinstance(value["$var"], str):
            yield path, value["$var"], "variable"
        for key, item in value.items():
            yield from _walk_params(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_params(item, f"{path}[{index}]")
    elif isinstance(value, str) and _absolute_path(value):
        yield path, value, "path"


def _validate_metanode(
    node: Node, declarations: Mapping[str, NodeDeclaration]
) -> list[ValidationIssue]:
    if node.type != "flow.metanode":
        return []
    issues: list[ValidationIssue] = []
    graph = node.params.get("graph")
    interface = node.params.get("interface")
    if not isinstance(graph, dict) or not isinstance(interface, dict):
        return [
            ValidationIssue("METANODE_INVALID", "Metanode requires graph and interface", node.id)
        ]
    internal_nodes = graph.get("nodes", [])
    internal_by_id = {item.get("id"): item for item in internal_nodes if isinstance(item, dict)}
    external_names: set[str] = set()
    external_declaration = declarations.get(node.type)
    for direction in ("inputs", "outputs"):
        mappings = interface.get(direction, {})
        if not isinstance(mappings, dict):
            issues.append(
                ValidationIssue("METANODE_INVALID", "Metanode interface must be an object", node.id)
            )
            continue
        for name, mapping in mappings.items():
            if name in external_names:
                issues.append(
                    ValidationIssue(
                        "METANODE_PORT_DUPLICATE", f"Metanode port '{name}' is duplicated", node.id
                    )
                )
            external_names.add(name)
            if (
                not isinstance(mapping, dict)
                or mapping.get("node") not in internal_by_id
                or not mapping.get("port")
            ):
                issues.append(
                    ValidationIssue(
                        "METANODE_PORT_MISSING",
                        f"Metanode port '{name}' maps to a missing internal node or port",
                        node.id,
                    )
                )
                continue
            internal_node = internal_by_id[mapping["node"]]
            internal_type = internal_node.get("type")
            internal_declaration = (
                declarations.get(internal_type) if isinstance(internal_type, str) else None
            )
            if external_declaration is None or internal_declaration is None:
                continue
            external_ports = getattr(external_declaration, direction)
            internal_ports = getattr(internal_declaration, direction)
            external_port = next((item for item in external_ports if item.name == name), None)
            internal_port = next(
                (item for item in internal_ports if item.name == mapping["port"]), None
            )
            if external_port is None or internal_port is None:
                issues.append(
                    ValidationIssue(
                        "METANODE_PORT_MISSING",
                        f"Metanode port '{name}' maps to a missing internal port",
                        node.id,
                    )
                )
            elif external_port.kind != internal_port.kind:
                issues.append(
                    ValidationIssue(
                        "METANODE_PORT_INCOMPATIBLE",
                        f"Metanode port '{name}' type does not match its internal port",
                        node.id,
                    )
                )
    for raw_edge in graph.get("edges", []):
        try:
            edge = Edge.model_validate(raw_edge)
            source = internal_by_id[edge.source]
            target = internal_by_id[edge.target]
            source_type = source.get("type")
            target_type = target.get("type")
            if not isinstance(source_type, str) or not isinstance(target_type, str):
                raise ValueError("missing internal node type")
            source_declaration = declarations.get(source_type)
            target_declaration = declarations.get(target_type)
            source_port = next(
                (
                    item
                    for item in (source_declaration.outputs if source_declaration else [])
                    if item.name == edge.sourcePort
                ),
                None,
            )
            target_port = next(
                (
                    item
                    for item in (target_declaration.inputs if target_declaration else [])
                    if item.name == edge.targetPort
                ),
                None,
            )
            if source_port is None or target_port is None:
                raise ValueError("missing internal port")
            if not is_compatible(source_port.kind, target_port.kind):
                raise ValueError("incompatible internal ports")
        except (KeyError, ValueError) as exception:
            issues.append(
                ValidationIssue(
                    "METANODE_INVALID", f"Metanode contains an invalid edge: {exception}", node.id
                )
            )
    return issues


def _validate_loops(document: WorkflowDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    starts = [node for node in document.nodes if node.type == "flow.loop_start"]
    ends = [node for node in document.nodes if node.type == "flow.loop_end"]
    end_pairs = {node.params.get("loop_id") for node in ends}
    start_pairs = {node.params.get("loop_id") for node in starts}
    for node in starts:
        pair = node.params.get("loop_id")
        if not pair or pair not in end_pairs:
            issues.append(ValidationIssue("LOOP_UNMATCHED", "Loop Start 无匹配 Loop End", node.id))
    for node in ends:
        pair = node.params.get("loop_id")
        if not pair or pair not in start_pairs:
            issues.append(ValidationIssue("LOOP_UNMATCHED", "Loop End 无匹配 Loop Start", node.id))
    if len(start_pairs) != len(starts) or len(end_pairs) != len(ends):
        issues.append(
            ValidationIssue("LOOP_NESTING", "Loop pairs must be unique and legally nested")
        )
    return issues


def _validate_acyclic(document: WorkflowDocument) -> list[ValidationIssue]:
    loop_nodes = {
        node.id: f"loop:{node.params.get('loop_id')}"
        for node in document.nodes
        if node.type in {"flow.loop_start", "flow.loop_end"}
    }
    successors: dict[str, set[str]] = defaultdict(set)
    for raw_edge in document.edges:
        edge = Edge.model_validate(raw_edge)
        successors[edge.source].add(edge.target)
    for start in document.nodes:
        if start.type != "flow.loop_start":
            continue
        pair = start.params.get("loop_id")
        end = next(
            (
                node.id
                for node in document.nodes
                if node.type == "flow.loop_end" and node.params.get("loop_id") == pair
            ),
            None,
        )
        pending = list(successors[start.id])
        while pending:
            current = pending.pop()
            if current == end or current in loop_nodes:
                continue
            loop_nodes[current] = f"loop:{pair}"
            pending.extend(successors[current])
    adjacency: dict[str, set[str]] = defaultdict(set)
    nodes = {node.id for node in document.nodes}
    for raw_edge in document.edges:
        edge = Edge.model_validate(raw_edge)
        source = loop_nodes.get(edge.source, edge.source)
        target = loop_nodes.get(edge.target, edge.target)
        if source != target or edge.source == edge.target:
            adjacency[source].add(target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(target) for target in adjacency[node]):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    if any(visit(node) for node in nodes | set(adjacency)):
        return [ValidationIssue("GRAPH_CYCLE", "不允许形成循环，请使用 Loop 节点")]
    return []


def validate_workflow(
    document: WorkflowDocument, declarations: Mapping[str, NodeDeclaration]
) -> ValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    node_by_id = {node.id: node for node in document.nodes}
    incoming: dict[tuple[str, str], list[Edge]] = defaultdict(list)
    variable_names = {variable.name for variable in document.variables}
    for node in document.nodes:
        if node.type not in declarations and node.type not in {
            "flow.loop_start",
            "flow.loop_end",
            "flow.metanode",
        }:
            warnings.append(
                ValidationIssue("UNKNOWN_NODE", f"未知节点类型 {node.type}，不可执行", node.id)
            )
        for path, value, kind in _walk_params(node.params):
            if kind == "variable" and value not in variable_names:
                warnings.append(
                    ValidationIssue(
                        "VARIABLE_UNKNOWN", f"Flow variable '{value}' may not exist", node.id
                    )
                )
            elif kind == "path":
                warnings.append(
                    ValidationIssue("ABSOLUTE_PATH", f"绝对路径不可移植: {path}={value}", node.id)
                )
        errors.extend(_validate_metanode(node, declarations))
    for raw_edge in document.edges:
        edge = Edge.model_validate(raw_edge)
        source = node_by_id.get(edge.source)
        target = node_by_id.get(edge.target)
        if source is None or target is None:
            errors.append(
                ValidationIssue("EDGE_NODE_MISSING", f"Edge {edge.id} references a missing node")
            )
            continue
        _, source_outputs = _ports(source, declarations)
        target_inputs, _ = _ports(target, declarations)
        source_kind = source_outputs.get(edge.sourcePort)
        target_kind = target_inputs.get(edge.targetPort)
        if source_kind is None or target_kind is None:
            errors.append(
                ValidationIssue("EDGE_PORT_MISSING", f"Edge {edge.id} references a missing port")
            )
            continue
        if not is_compatible(source_kind, target_kind):
            errors.append(
                ValidationIssue(
                    "PORT_INCOMPATIBLE", f"{source_kind} 端口不能连接到 {target_kind} 端口"
                )
            )
        incoming[(edge.target, edge.targetPort)].append(edge)
    for (target_id, port_name), edges in incoming.items():
        target = node_by_id[target_id]
        inputs, _ = _ports(target, declarations)
        port_kind = inputs.get(port_name)
        if port_kind not in {"tool", "variable"} and len(edges) > 1:
            errors.append(
                ValidationIssue(
                    "PORT_CARDINALITY",
                    f"Input {target_id}.{port_name} allows at most one incoming edge",
                )
            )
        orders = [edge.order for edge in edges]
        if len(orders) != len(set(orders)):
            errors.append(
                ValidationIssue(
                    "EDGE_ORDER", f"Input {target_id}.{port_name} requires unique edge order values"
                )
            )
    errors.extend(_validate_loops(document))
    errors.extend(_validate_acyclic(document))
    return ValidationReport(tuple(errors), tuple(warnings))
