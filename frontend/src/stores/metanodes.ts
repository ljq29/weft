import type { FlowEdge, FlowNode } from "./workflowStore";
import type { CanvasNote, NodeTypeDecl, PortDecl } from "../types/workflow";

interface Mapping {
  node: string;
  port: string;
}
interface MetanodeParams {
  graph: {
    nodes: {
      id: string;
      type: string;
      name: string;
      position: { x: number; y: number };
      params: Record<string, unknown>;
      comment?: string;
    }[];
    edges: {
      id: string;
      source: string;
      sourcePort: string;
      target: string;
      targetPort: string;
      order: number;
    }[];
    notes?: CanvasNote[];
  };
  interface: {
    inputs: Record<string, Mapping>;
    outputs: Record<string, Mapping>;
  };
}

function internalNode(params: MetanodeParams, id: string) {
  const node = params.graph.nodes.find((item) => item.id === id);
  if (!node) throw new Error("Metanode 内部节点不存在");
  return node;
}

export function metanodePorts(
  params: Record<string, unknown>,
  types: NodeTypeDecl[],
): { inputs: PortDecl[]; outputs: PortDecl[] } {
  const meta = params as unknown as MetanodeParams;
  const result: { inputs: PortDecl[]; outputs: PortDecl[] } = {
    inputs: [],
    outputs: [],
  };
  for (const direction of ["inputs", "outputs"] as const) {
    for (const [name, mapping] of Object.entries(meta.interface[direction])) {
      const target = internalNode(meta, mapping.node);
      const declaration = types.find((item) => item.type === target.type);
      const port = declaration?.[direction].find(
        (item) => item.name === mapping.port,
      );
      if (!port)
        throw new Error(
          `Metanode 内部端口不存在: ${target.type}.${mapping.port} (${direction})`,
        );
      result[direction].push({ ...port, name });
    }
  }
  return result;
}

export function flowGraph(
  params: Record<string, unknown>,
  types: NodeTypeDecl[],
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const meta = params as unknown as MetanodeParams;
  return {
    nodes: [
      ...meta.graph.nodes.map((node) => ({
        id: node.id,
        type: "weft",
        position: node.position,
        data: {
          nodeId: node.id,
          type: node.type,
          name: node.name,
          params: node.params,
          inputs:
            node.type === "flow.metanode"
              ? metanodePorts(node.params, types).inputs
              : (types.find((item) => item.type === node.type)?.inputs ?? []),
          outputs:
            node.type === "flow.metanode"
              ? metanodePorts(node.params, types).outputs
              : (types.find((item) => item.type === node.type)?.outputs ?? []),
          comment: node.comment ?? "",
          status: "configured",
        },
      })),
      ...(meta.graph.notes ?? []).map((note) => ({
        id: note.id,
        type: "note",
        position: note.position,
        data: {
          nodeId: note.id,
          type: "canvas.note",
          name: "便签",
          params: {
            markdown: note.markdown,
            color: note.color,
            width: note.size.width,
            height: note.size.height,
          },
          inputs: [],
          outputs: [],
          comment: "",
          status: "configured",
        },
      })),
    ],
    edges: meta.graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      sourceHandle: edge.sourcePort,
      target: edge.target,
      targetHandle: edge.targetPort,
    })),
  };
}

function uniqueName(base: string, used: Set<string>): string {
  const normalized = base.replaceAll(/[^A-Za-z0-9_]/g, "_") || "port";
  let name = normalized;
  let index = 2;
  while (used.has(name)) name = `${normalized}_${String(index++)}`;
  used.add(name);
  return name;
}

export function collapseGraph(
  nodes: FlowNode[],
  edges: FlowEdge[],
  selected: string[],
  types: NodeTypeDecl[],
  metaId: string,
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const chosen = nodes.filter((node) => selected.includes(node.id));
  if (!chosen.length) return { nodes, edges };
  const params: MetanodeParams = {
    graph: {
      nodes: chosen.map((node) => ({
        id: node.id,
        type: node.data.type,
        name: node.data.name,
        position: node.position,
        params: structuredClone(node.data.params),
        comment: node.data.comment,
      })),
      edges: edges
        .filter(
          (edge) =>
            selected.includes(edge.source) && selected.includes(edge.target),
        )
        .map((edge, order) => ({
          id: edge.id,
          source: edge.source,
          sourcePort: edge.sourceHandle ?? "",
          target: edge.target,
          targetPort: edge.targetHandle ?? "",
          order,
        })),
    },
    interface: { inputs: {}, outputs: {} },
  };
  const used = new Set<string>();
  const crossing = edges.filter(
    (edge) => selected.includes(edge.source) !== selected.includes(edge.target),
  );
  const external = crossing.map((edge) => {
    const incoming = selected.includes(edge.target);
    const mapping: Mapping = incoming
      ? { node: edge.target, port: edge.targetHandle ?? "" }
      : { node: edge.source, port: edge.sourceHandle ?? "" };
    const name = uniqueName(`${incoming ? "in" : "out"}_${mapping.port}`, used);
    params.interface[incoming ? "inputs" : "outputs"][name] = mapping;
    return {
      ...edge,
      source: incoming ? edge.source : metaId,
      sourceHandle: incoming ? edge.sourceHandle : name,
      target: incoming ? metaId : edge.target,
      targetHandle: incoming ? name : edge.targetHandle,
    };
  });
  const ports = metanodePorts(
    params as unknown as Record<string, unknown>,
    types,
  );
  const meta: FlowNode = {
    id: metaId,
    type: "weft",
    position: { ...chosen[0].position },
    data: {
      nodeId: metaId,
      type: "flow.metanode",
      name: `Metanode ${metaId.slice(-4)}`,
      params: params as unknown as Record<string, unknown>,
      inputs: ports.inputs,
      outputs: ports.outputs,
      comment: "",
      status: "configured",
    },
  };
  return {
    nodes: [...nodes.filter((node) => !selected.includes(node.id)), meta],
    edges: [
      ...edges.filter(
        (edge) =>
          !selected.includes(edge.source) && !selected.includes(edge.target),
      ),
      ...external,
    ],
  };
}

export function expandGraph(
  nodes: FlowNode[],
  edges: FlowEdge[],
  metaId: string,
  types: NodeTypeDecl[],
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const meta = nodes.find((node) => node.id === metaId);
  if (!meta || meta.data.type !== "flow.metanode") return { nodes, edges };
  const params = meta.data.params as unknown as MetanodeParams;
  const internal = flowGraph(meta.data.params, types);
  const crossing = edges.filter(
    (edge) => edge.source === metaId || edge.target === metaId,
  );
  const restored = crossing.map((edge) => {
    const incoming = edge.target === metaId;
    const mapping = params.interface[incoming ? "inputs" : "outputs"][
      (incoming ? edge.targetHandle : edge.sourceHandle) ?? ""
    ] as Mapping | undefined;
    if (!mapping) throw new Error("Metanode 外部端口映射不存在");
    return {
      ...edge,
      source: incoming ? edge.source : mapping.node,
      sourceHandle: incoming ? edge.sourceHandle : mapping.port,
      target: incoming ? mapping.node : edge.target,
      targetHandle: incoming ? mapping.port : edge.targetHandle,
    };
  });
  return {
    nodes: [...nodes.filter((node) => node.id !== metaId), ...internal.nodes],
    edges: [
      ...edges.filter(
        (edge) => edge.source !== metaId && edge.target !== metaId,
      ),
      ...internal.edges,
      ...restored,
    ],
  };
}
