import {
  useCallback,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import type {
  Connection,
  Edge,
  ReactFlowInstance,
  Viewport,
} from "@xyflow/react";
import { api } from "../api/client";
import { collapseGraph, expandGraph, flowGraph } from "../stores/metanodes";
import {
  toDocument,
  useWorkflowStore,
  type FlowEdge,
  type FlowNode,
} from "../stores/workflowStore";
import type { GraphStackEntry } from "./useWorkflowDocument";

interface CanvasInteractionsOptions {
  flow: ReactFlowInstance<FlowNode, FlowEdge>;
  viewport: { current: Viewport };
  graphStack: { current: GraphStackEntry[] };
  setBreadcrumbs: Dispatch<SetStateAction<{ id: string; name: string }[]>>;
  setError: (error: string) => void;
}

export function useCanvasInteractions({
  flow,
  viewport,
  graphStack,
  setBreadcrumbs,
  setError,
}: CanvasInteractionsOptions) {
  const [menu, setMenu] = useState<{
    nodeId: string;
    x: number;
    y: number;
  } | null>(null);
  const [columnHints, setColumnHints] = useState<string[]>([]);

  const collapse = useCallback(() => {
    const state = useWorkflowStore.getState();
    const selected = state.selected.filter(
      (id) =>
        state.nodes.find((node) => node.id === id)?.data.type !== "canvas.note",
    );
    if (!selected.length) return;
    const metaId = `n_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
    const graph = collapseGraph(
      state.nodes,
      state.edges,
      selected,
      state.nodeTypes,
      metaId,
    );
    state.setGraph(graph.nodes, graph.edges);
    state.setSelected([metaId]);
  }, []);

  const expand = useCallback((nodeId: string) => {
    const state = useWorkflowStore.getState();
    const graph = expandGraph(
      state.nodes,
      state.edges,
      nodeId,
      state.nodeTypes,
    );
    state.setGraph(graph.nodes, graph.edges);
    setMenu(null);
  }, []);

  const enterMetanode = useCallback(
    (node: FlowNode) => {
      if (node.data.type !== "flow.metanode") return;
      const state = useWorkflowStore.getState();
      const graph = flowGraph(node.data.params, state.nodeTypes);
      graphStack.current.push({
        nodes: state.nodes,
        edges: state.edges,
        id: node.id,
        name: node.data.name,
      });
      setBreadcrumbs([
        ...graphStack.current.map((item) => ({ id: item.id, name: item.name })),
      ]);
      useWorkflowStore.setState({
        nodes: graph.nodes,
        edges: graph.edges,
        selected: [],
        history: [],
        future: [],
        dirty: false,
      });
    },
    [graphStack, setBreadcrumbs],
  );

  const leaveMetanode = useCallback(() => {
    const parent = graphStack.current.pop();
    if (!parent) return;
    const state = useWorkflowStore.getState();
    const meta = parent.nodes.find((node) => node.id === parent.id);
    if (!meta) throw new Error("Metanode 不存在");
    const params = {
      ...meta.data.params,
      graph: {
        nodes: state.nodes
          .filter((node) => node.data.type !== "canvas.note")
          .map((node) => ({
            id: node.id,
            type: node.data.type,
            name: node.data.name,
            position: node.position,
            params: node.data.params,
            comment: node.data.comment,
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
      },
    };
    useWorkflowStore.setState({
      nodes: parent.nodes.map((node) =>
        node.id === parent.id
          ? { ...node, data: { ...node.data, params } }
          : node,
      ),
      edges: parent.edges,
      selected: [parent.id],
      history: [],
      future: [],
      dirty: true,
    });
    setBreadcrumbs(
      graphStack.current.map((item) => ({ id: item.id, name: item.name })),
    );
  }, [graphStack, setBreadcrumbs]);

  const addAtCenter = useCallback(
    (type: string) => {
      useWorkflowStore.getState().addNode(
        type,
        flow.screenToFlowPosition({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
        }),
      );
    },
    [flow],
  );

  const connect = useCallback(
    async (connection: Connection) => {
      const edge: Edge = {
        ...connection,
        id: `e_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`,
      };
      const store = useWorkflowStore.getState();
      store.connect(edge);
      const state = useWorkflowStore.getState();
      if (!state.document) return;
      const report = await api<{ errors: { message: string }[] }>(
        `/workflows/${state.document.id}/validate`,
        {
          method: "POST",
          body: JSON.stringify(toDocument(state, viewport.current)),
        },
      );
      if (report.errors.length) {
        state.undo();
        setError(report.errors[0].message);
      }
    },
    [setError, viewport],
  );

  const selectNodes = useCallback((nodes: FlowNode[]) => {
    const updateHints = (next: string[]) => {
      setColumnHints((current) => {
        if (
          current.length === next.length &&
          current.every((value, index) => value === next[index])
        )
          return current;
        return next;
      });
    };
    const ids = nodes.map((node) => node.id);
    const state = useWorkflowStore.getState();
    state.setSelected(ids);
    const document = state.document;
    if (!document || ids.length !== 1) {
      updateHints([]);
      return;
    }
    void api<Record<string, string[]>>(
      `/workflows/${document.id}/nodes/${ids[0]}/column-hints`,
      { method: "POST" },
    )
      .then((hints) => {
        updateHints(Object.values(hints).flat());
      })
      .catch(() => {
        updateHints([]);
      });
  }, []);

  return {
    menu,
    setMenu,
    columnHints,
    collapse,
    expand,
    enterMetanode,
    leaveMetanode,
    addAtCenter,
    connect,
    selectNodes,
  };
}
