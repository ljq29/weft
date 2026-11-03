import { create } from "zustand";
import type { Edge, Node, Viewport } from "@xyflow/react";
import type {
  NodeTypeDecl,
  WorkflowDocument,
  WorkflowNodeData,
} from "../types/workflow";

export type FlowNode = Node<WorkflowNodeData>;
export type FlowEdge = Edge;

interface Snapshot {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

interface WorkflowState extends Snapshot {
  document: WorkflowDocument | null;
  nodeTypes: NodeTypeDecl[];
  selected: string[];
  dirty: boolean;
  history: Snapshot[];
  future: Snapshot[];
  clipboard: Snapshot | null;
  setDocument: (
    document: WorkflowDocument,
    nodes: FlowNode[],
    edges: FlowEdge[],
  ) => void;
  setGraph: (nodes: FlowNode[], edges: FlowEdge[]) => void;
  setNodeTypes: (types: NodeTypeDecl[]) => void;
  setSelected: (ids: string[]) => void;
  addNode: (type: string, position: { x: number; y: number }) => void;
  addNote: (position: { x: number; y: number }) => void;
  updateComment: (id: string, comment: string) => void;
  updateParams: (id: string, params: Record<string, unknown>) => void;
  connect: (edge: FlowEdge) => void;
  moveNodes: (nodes: FlowNode[]) => void;
  deleteSelected: () => void;
  copy: () => void;
  paste: () => void;
  undo: () => void;
  redo: () => void;
  markSaved: (revision: number) => void;
}

const clone = <T>(value: T): T => structuredClone(value);
const id = (prefix: string) =>
  `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;

function defaults(type: NodeTypeDecl | undefined): Record<string, unknown> {
  const properties = type?.params_schema.properties ?? {};
  return Object.fromEntries(
    Object.entries(properties).map(([key, value]) => {
      const schema = value as Record<string, unknown>;
      return [
        key,
        schema.default ??
          (schema.type === "boolean"
            ? false
            : schema.type === "array"
              ? []
              : ""),
      ];
    }),
  );
}

function configurationStatus(
  type: NodeTypeDecl | undefined,
  params: Record<string, unknown>,
): string {
  const required = (type?.params_schema.required as string[] | undefined) ?? [];
  return required.some(
    (name) => params[name] === "" || params[name] === undefined,
  )
    ? "unconfigured"
    : "configured";
}

export const useWorkflowStore = create<WorkflowState>((set, get) => {
  const change = (nodes: FlowNode[], edges: FlowEdge[]) => {
    const state = get();
    const previous = clone({ nodes: state.nodes, edges: state.edges });
    set({
      nodes,
      edges,
      dirty: true,
      history: [...state.history.slice(-49), previous],
      future: [],
    });
  };
  return {
    document: null,
    nodeTypes: [],
    nodes: [],
    edges: [],
    selected: [],
    dirty: false,
    history: [],
    future: [],
    clipboard: null,
    setDocument: (document, nodes, edges) => {
      set({
        document: clone(document),
        nodes,
        edges,
        dirty: false,
        history: [],
        future: [],
      });
    },
    setGraph: (nodes, edges) => {
      change(nodes, edges);
    },
    setNodeTypes: (nodeTypes) => {
      set({ nodeTypes });
    },
    setSelected: (selected) => {
      const current = get().selected;
      if (
        current.length === selected.length &&
        current.every((id, index) => id === selected[index])
      )
        return;
      set({ selected });
    },
    addNode: (type, position) => {
      const state = get();
      const declaration = state.nodeTypes.find((item) => item.type === type);
      const nodeId = id("n");
      const node: FlowNode = {
        id: nodeId,
        type: "weft",
        position,
        data: {
          nodeId,
          type,
          name: declaration?.name ?? type,
          params: defaults(declaration),
          inputs: declaration?.inputs ?? [],
          outputs: declaration?.outputs ?? [],
          comment: "",
          status: configurationStatus(declaration, defaults(declaration)),
        },
      };
      change([...state.nodes, node], state.edges);
    },
    addNote: (position) => {
      const state = get();
      const noteId = id("note");
      const note: FlowNode = {
        id: noteId,
        type: "note",
        position,
        data: {
          nodeId: noteId,
          type: "canvas.note",
          name: "便签",
          params: {
            markdown: "# 新便签\n双击此处编辑",
            color: "#fef3c7",
            width: 240,
            height: 160,
          },
          inputs: [],
          outputs: [],
          comment: "",
          status: "configured",
        },
      };
      change([...state.nodes, note], state.edges);
    },
    updateComment: (nodeId, comment) => {
      const state = get();
      change(
        state.nodes.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, comment } }
            : node,
        ),
        state.edges,
      );
    },
    updateParams: (nodeId, params) => {
      const state = get();
      const affected = new Set([nodeId]);
      let changed = true;
      while (changed) {
        changed = false;
        for (const edge of state.edges) {
          if (affected.has(edge.source) && !affected.has(edge.target)) {
            affected.add(edge.target);
            changed = true;
          }
        }
      }
      change(
        state.nodes.map((node) => {
          if (!affected.has(node.id)) return node;
          const nextParams = node.id === nodeId ? params : node.data.params;
          return {
            ...node,
            data: {
              ...node.data,
              params: nextParams,
              status: configurationStatus(
                state.nodeTypes.find((item) => item.type === node.data.type),
                nextParams,
              ),
            },
          };
        }),
        state.edges,
      );
    },
    connect: (edge) => {
      const state = get();
      const declaration = state.nodeTypes.find(
        (item) =>
          item.type ===
          state.nodes.find((node) => node.id === edge.target)?.data.type,
      );
      const targetPort = declaration?.inputs.find(
        (port) => port.name === edge.targetHandle,
      );
      const retained =
        targetPort?.kind === "variable" || targetPort?.kind === "tool"
          ? state.edges
          : state.edges.filter(
              (item) =>
                item.target !== edge.target ||
                item.targetHandle !== edge.targetHandle,
            );
      change([...state.nodes], [...retained, edge]);
    },
    moveNodes: (nodes) => {
      const previous = get().nodes;
      const changed =
        nodes.length !== previous.length ||
        nodes.some(
          (node, index) =>
            previous[index]?.id !== node.id ||
            previous[index]?.position.x !== node.position.x ||
            previous[index]?.position.y !== node.position.y,
        );
      if (changed) change(nodes, get().edges);
      else set({ nodes });
    },
    deleteSelected: () => {
      const state = get();
      change(
        state.nodes.filter((node) => !state.selected.includes(node.id)),
        state.edges.filter(
          (edge) =>
            !state.selected.includes(edge.source) &&
            !state.selected.includes(edge.target),
        ),
      );
    },
    copy: () => {
      const state = get();
      const nodes = state.nodes.filter((node) =>
        state.selected.includes(node.id),
      );
      const ids = nodes.map((node) => node.id);
      set({
        clipboard: clone({
          nodes,
          edges: state.edges.filter(
            (edge) => ids.includes(edge.source) && ids.includes(edge.target),
          ),
        }),
      });
    },
    paste: () => {
      const state = get();
      if (!state.clipboard) return;
      const mapping = new Map(
        state.clipboard.nodes.map((node) => [node.id, id("n")]),
      );
      const nodes = state.clipboard.nodes.map((node) => {
        const nodeId = mapping.get(node.id);
        if (!nodeId) throw new Error("Missing copied node id");
        return {
          ...clone(node),
          id: nodeId,
          position: { x: node.position.x + 40, y: node.position.y + 40 },
          data: { ...node.data, nodeId, name: node.data.name },
        };
      });
      const edges = state.clipboard.edges.map((edge) => {
        const source = mapping.get(edge.source);
        const target = mapping.get(edge.target);
        if (!source || !target) throw new Error("Missing copied edge endpoint");
        return { ...clone(edge), id: id("e"), source, target };
      });
      change([...state.nodes, ...nodes], [...state.edges, ...edges]);
    },
    undo: () => {
      const state = get();
      const previous = state.history.at(-1);
      if (!previous) return;
      const current = clone({ nodes: state.nodes, edges: state.edges });
      set({
        nodes: previous.nodes,
        edges: previous.edges,
        history: state.history.slice(0, -1),
        future: [current, ...state.future],
        dirty: true,
      });
    },
    redo: () => {
      const state = get();
      if (state.future.length === 0) return;
      const next = state.future[0];
      const current = clone({ nodes: state.nodes, edges: state.edges });
      set({
        nodes: next.nodes,
        edges: next.edges,
        future: state.future.slice(1),
        history: [...state.history, current],
        dirty: true,
      });
    },
    markSaved: (revision) => {
      const document = get().document;
      set({
        dirty: false,
        document: document ? { ...document, revision } : null,
      });
    },
  };
});

export function toDocument(
  state: WorkflowState,
  viewport: Viewport,
): Record<string, unknown> {
  if (!state.document) throw new Error("No workflow open");
  return {
    ...state.document,
    settings: state.document.settings,
    variables: state.document.variables,
    nodes: state.nodes
      .filter((node) => node.data.type !== "canvas.note")
      .map((node) => ({
        id: node.id,
        type: node.data.type,
        node_version: 1,
        name: node.data.name,
        position: node.position,
        comment: node.data.comment,
        params: node.data.params,
      })),
    notes: state.nodes
      .filter((node) => node.data.type === "canvas.note")
      .map((node) => ({
        id: node.id,
        position: node.position,
        size: {
          width: Number(node.data.params.width ?? 240),
          height: Number(node.data.params.height ?? 160),
        },
        color:
          typeof node.data.params.color === "string"
            ? node.data.params.color
            : "#fef3c7",
        markdown:
          typeof node.data.params.markdown === "string"
            ? node.data.params.markdown
            : "",
      })),
    edges: state.edges.map((edge, order) => ({
      id: edge.id,
      source: edge.source,
      sourcePort: edge.sourceHandle,
      target: edge.target,
      targetPort: edge.targetHandle,
      order,
    })),
    viewport,
  };
}
