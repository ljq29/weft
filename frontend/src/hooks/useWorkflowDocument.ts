import { useCallback, useEffect, useRef, useState } from "react";
import type { Viewport } from "@xyflow/react";
import { ApiError, api, formatApiError } from "../api/client";
import { metanodePorts } from "../stores/metanodes";
import {
  toDocument,
  useWorkflowStore,
  type FlowEdge,
  type FlowNode,
  type ValidationIssue,
} from "../stores/workflowStore";
import type { WorkflowDocument } from "../types/workflow";

interface StoredNode {
  id: string;
  type: string;
  name: string;
  position: { x: number; y: number };
  params: Record<string, unknown>;
  comment?: string;
}

interface StoredEdge {
  id: string;
  source: string;
  sourcePort: string;
  target: string;
  targetPort: string;
}

export interface GraphStackEntry {
  nodes: FlowNode[];
  edges: FlowEdge[];
  id: string;
  name: string;
}

interface ValidationReport {
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
}

let saveQueue: Promise<void> = Promise.resolve();

export function useWorkflowDocument({
  setError,
}: {
  setError: (error: string) => void;
}) {
  const dirty = useWorkflowStore((state) => state.dirty);
  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const viewport = useRef<Viewport>({ x: 0, y: 0, zoom: 1 });
  const graphStack = useRef<GraphStackEntry[]>([]);
  const [breadcrumbs, setBreadcrumbs] = useState<
    { id: string; name: string }[]
  >([]);
  const [revisionConflict, setRevisionConflict] = useState(false);

  const save = useCallback(() => {
    const operation = saveQueue.then(async () => {
      const state = useWorkflowStore.getState();
      if (!state.document || graphStack.current.length) return;
      try {
        const document = toDocument(state, viewport.current);
        const saved = await api<WorkflowDocument>(
          `/workflows/${state.document.id}`,
          { method: "PUT", body: JSON.stringify(document) },
        );
        state.markSaved(saved.revision);
        setRevisionConflict(false);
        setError("");
        const report = await api<ValidationReport>(
          `/workflows/${state.document.id}/validate`,
        );
        state.applyValidation([...report.errors, ...report.warnings]);
      } catch (reason) {
        if (
          reason instanceof ApiError &&
          reason.status === 409 &&
          reason.code === "REVISION_CONFLICT"
        ) {
          setRevisionConflict(true);
        }
        setError(formatApiError(reason));
      }
    });
    saveQueue = operation;
    return operation;
  }, [setError]);

  const load = useCallback(
    (document: WorkflowDocument & { nodes: unknown[]; edges: unknown[] }) => {
      const state = useWorkflowStore.getState();
      const selectedIds =
        state.document?.id === document.id ? state.selected : [];
      const declarations = new Map(
        state.nodeTypes.map((item) => [item.type, item]),
      );
      graphStack.current = [];
      setBreadcrumbs([]);
      const nodes = document.nodes.map((raw) => {
        const node = raw as StoredNode;
        const ports =
          node.type === "flow.metanode"
            ? metanodePorts(node.params, state.nodeTypes)
            : {
                inputs: declarations.get(node.type)?.inputs ?? [],
                outputs: declarations.get(node.type)?.outputs ?? [],
              };
        return {
          id: node.id,
          type: "weft",
          position: node.position,
          selected: selectedIds.includes(node.id),
          data: {
            nodeId: node.id,
            type: node.type,
            name: node.name,
            params: node.params,
            inputs: ports.inputs,
            outputs: ports.outputs,
            comment: node.comment ?? "",
            status: "configured",
          },
        };
      });
      const notes: FlowNode[] = document.notes.map((note) => ({
        id: note.id,
        type: "note",
        position: note.position,
        selected: selectedIds.includes(note.id),
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
      }));
      const edges = document.edges.map((raw) => {
        const edge = raw as StoredEdge;
        return {
          id: edge.id,
          source: edge.source,
          sourceHandle: edge.sourcePort,
          target: edge.target,
          targetHandle: edge.targetPort,
        };
      });
      state.setDocument(document, [...nodes, ...notes], edges);
      state.setSelected(selectedIds);
      viewport.current = document.viewport;
      setRevisionConflict(false);
    },
    [],
  );

  const reload = useCallback(async () => {
    const id = useWorkflowStore.getState().document?.id;
    if (!id) return;
    try {
      const document = await api<
        WorkflowDocument & { nodes: unknown[]; edges: unknown[] }
      >(`/workflows/${id}`);
      if (useWorkflowStore.getState().document?.id !== id) return;
      load(document);
      setError("");
    } catch (reason) {
      setError(formatApiError(reason));
    }
  }, [load, setError]);

  useEffect(() => {
    if (!dirty) return;
    const timer = window.setTimeout(() => {
      void save();
    }, 2000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [dirty, nodes, edges, save]);

  return {
    save,
    load,
    reload,
    revisionConflict,
    viewport,
    graphStack,
    breadcrumbs,
    setBreadcrumbs,
  };
}
