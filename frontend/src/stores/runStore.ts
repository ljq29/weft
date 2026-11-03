import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import type { TraceEntry } from "../panels/TracePanel";

function text(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return value.toString();
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return fallback;
}

interface LogEntry {
  node_id: string;
  level: string;
  message: string;
}
interface NodeError {
  message: string;
  traceback?: string;
}
interface RunEvent {
  event: string;
  data: Record<string, unknown>;
}
interface RunState {
  runId: string;
  statuses: Record<string, string>;
  errors: Record<string, NodeError>;
  logs: LogEntry[];
  iterations: Record<string, { index: number; total: number }>;
  traces: Record<string, TraceEntry[]>;
  started: (runId: string) => void;
  apply: (event: RunEvent) => void;
  snapshot: (record: {
    nodes: Record<string, { status: string; error?: NodeError }>;
  }) => void;
  reset: () => void;
}

export const useRunStore = create<RunState>()(
  subscribeWithSelector((set) => ({
    runId: "",
    statuses: {},
    errors: {},
    logs: [],
    iterations: {},
    traces: {},
    started: (runId) => {
      set({
        runId,
        statuses: {},
        errors: {},
        logs: [],
        iterations: {},
        traces: {},
      });
    },
    apply: ({ event, data }) => {
      set((state) => {
        const nodeId = text(data.node_id);
        const statuses = { ...state.statuses };
        const errors = { ...state.errors };
        let logs = state.logs;
        let iterations = state.iterations;
        let traces = state.traces;
        if (event === "node.stream")
          traces = {
            ...traces,
            [nodeId]: [...(traces[nodeId] ?? []), { type: "stream", ...data }],
          };
        if (event === "node.tool_call")
          traces = {
            ...traces,
            [nodeId]: [...(traces[nodeId] ?? []), { type: "tool", ...data }],
          };
        if (event === "node.llm_trace")
          traces = {
            ...traces,
            [nodeId]: [...(traces[nodeId] ?? []), { type: "llm", ...data }],
          };
        if (event === "node.iteration")
          iterations = {
            ...iterations,
            [nodeId]: { index: Number(data.index), total: Number(data.total) },
          };
        if (event === "node.started") statuses[nodeId] = "running";
        if (event === "node.status") statuses[nodeId] = text(data.status);
        if (event === "node.finished") statuses[nodeId] = "executed";
        if (event === "node.failed") {
          statuses[nodeId] = "failed";
          errors[nodeId] = (data.error as NodeError | undefined) ?? {
            message: text(data.message, "执行失败"),
          };
        }
        if (event === "node.log")
          logs = [
            ...logs,
            {
              node_id: nodeId,
              level: text(data.level, "INFO"),
              message: text(data.message),
            },
          ];
        return { statuses, errors, logs, iterations, traces };
      });
    },
    snapshot: (record) => {
      const statuses = Object.fromEntries(
        Object.entries(record.nodes).map(([id, node]) => [id, node.status]),
      );
      const errors = Object.fromEntries(
        Object.entries(record.nodes).flatMap(([id, node]) =>
          node.error ? [[id, node.error]] : [],
        ),
      );
      set({ statuses, errors });
    },
    reset: () => {
      set({
        runId: "",
        statuses: {},
        errors: {},
        logs: [],
        iterations: {},
        traces: {},
      });
    },
  })),
);
