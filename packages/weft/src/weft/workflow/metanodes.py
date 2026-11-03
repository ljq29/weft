from __future__ import annotations

from typing import Any

from weft.workflow.models import Edge, Node, WorkflowDocument
from weft.workflow.validation import NodeDeclaration, PortDeclaration


def _runtime_id(prefix: str, node_id: str) -> str:
    return f"{prefix}{node_id}"


def _resolve_endpoint(
    node: Node,
    port: str,
    direction: str,
    prefix: str,
) -> tuple[str, str]:
    if node.type != "flow.metanode":
        return _runtime_id(prefix, node.id), port
    mapping = node.params["interface"][direction][port]
    internal = next(item for item in node.params["graph"]["nodes"] if item["id"] == mapping["node"])
    return _resolve_endpoint(
        Node.model_validate(internal),
        mapping["port"],
        direction,
        f"{prefix}meta_{node.id}/",
    )


def _expand_graph(
    nodes: list[Node], edges: list[Edge], prefix: str
) -> tuple[list[Node], list[Edge]]:
    expanded_nodes: list[Node] = []
    expanded_edges: list[Edge] = []
    by_id = {node.id: node for node in nodes}
    for node in nodes:
        if node.type != "flow.metanode":
            expanded_nodes.append(node.model_copy(update={"id": _runtime_id(prefix, node.id)}))
            continue
        graph = node.params["graph"]
        internal_nodes = [Node.model_validate(item) for item in graph["nodes"]]
        internal_edges = [Edge.model_validate(item) for item in graph.get("edges", [])]
        children, child_edges = _expand_graph(
            internal_nodes, internal_edges, f"{prefix}meta_{node.id}/"
        )
        expanded_nodes.extend(children)
        expanded_edges.extend(child_edges)
    for edge in edges:
        source, source_port = _resolve_endpoint(
            by_id[edge.source], edge.sourcePort, "outputs", prefix
        )
        target, target_port = _resolve_endpoint(
            by_id[edge.target], edge.targetPort, "inputs", prefix
        )
        expanded_edges.append(
            edge.model_copy(
                update={
                    "id": _runtime_id(prefix, edge.id),
                    "source": source,
                    "sourcePort": source_port,
                    "target": target,
                    "targetPort": target_port,
                }
            )
        )
    return expanded_nodes, expanded_edges


def expand_metanodes(workflow: WorkflowDocument) -> WorkflowDocument:
    nodes, edges = _expand_graph(workflow.nodes, workflow.edges, "")
    return workflow.model_copy(update={"nodes": nodes, "edges": edges})


def metanode_declaration(node: Any, params: dict[str, Any], registry: Any) -> NodeDeclaration:
    graph = params.get("graph", {})
    interface = params.get("interface", {})
    internal = {item["id"]: Node.model_validate(item) for item in graph.get("nodes", [])}
    ports: dict[str, list[PortDeclaration]] = {"inputs": [], "outputs": []}
    for direction in ("inputs", "outputs"):
        for name, mapping in interface.get(direction, {}).items():
            target = internal[mapping["node"]]
            declaration = registry.declaration(target.type, target.params)
            declarations = declaration.inputs if direction == "inputs" else declaration.outputs
            mapped = next(item for item in declarations if item.name == mapping["port"])
            ports[direction].append(PortDeclaration(name, mapped.kind))
    return NodeDeclaration(node.type, ports["inputs"], ports["outputs"])
