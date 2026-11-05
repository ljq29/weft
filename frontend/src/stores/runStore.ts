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

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
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
export interface RunEvent {
  event: string;
  data: Record<string, unknown>;
}
export interface ConfirmRequest {
  request_id: string;
  run_id: string;
  node_id: string;
  tool: string;
  args: Record<string, unknown>;
  timeout_at?: string;
}
export interface RunBaseline {
  run_id: string;
  status: string;
  workflow_id?: string;
  nodes: Record<string, { status: string; error?: NodeError }>;
}
export interface RunLogEntry {
  event: string;
  node_id?: string;
  ts?: string;
  data: Record<string, unknown>;
}
interface RunState {
  runId: string;
  runStatus: string;
  statuses: Record<string, string>;
  errors: Record<string, NodeError>;
  logs: LogEntry[];
  iterations: Record<string, { index: number; total: number }>;
  traces: Record<string, TraceEntry[]>;
  pendingConfirmations: ConfirmRequest[];
  started: (runId: string) => void;
  apply: (event: RunEvent) => void;
  snapshot: (record: {
    nodes: Record<string, { status: string; error?: NodeError }>;
  }) => void;
  baseline: (record: RunBaseline | null, entries: RunLogEntry[]) => void;
  reset: () => void;
}

const handledEvents = new Set([
  "run.started",
  "run.queued",
  "run.dequeued",
  "run.finished",
  "node.stream",
  "node.tool_call",
  "node.llm_trace",
  "node.iteration",
  "node.started",
  "node.status",
  "node.finished",
  "node.failed",
  "node.log",
  "node.confirm_request",
  "node.confirm_resolved",
]);

function emptyRun(runId = "", runStatus = "") {
  return {
    runId,
    runStatus,
    statuses: {},
    errors: {},
    logs: [],
    iterations: {},
    traces: {},
    pendingConfirmations: [],
  };
}

function eventNodeId(data: Record<string, unknown>): string {
  return text(data.node_id || data.loop_node_id);
}

export const useRunStore = create<RunState>()(
  subscribeWithSelector((set) => ({
    ...emptyRun(),
    started: (runId) => {
      set(emptyRun(runId, "running"));
    },
    apply: ({ event, data }) => {
      if (!handledEvents.has(event)) return;
      set((state) => {
        const eventRunId = text(data.run_id);
        if (
          (event === "run.started" || event === "run.queued") &&
          eventRunId &&
          eventRunId !== state.runId
        ) {
          return emptyRun(
            eventRunId,
            event === "run.queued" ? "queued" : "running",
          );
        }
        const nodeId = eventNodeId(data);
        const statuses = { ...state.statuses };
        const errors = { ...state.errors };
        let runStatus = state.runStatus;
        let logs = state.logs;
        let iterations = state.iterations;
        let traces = state.traces;
        let pendingConfirmations = state.pendingConfirmations;
        if (event === "run.started" || event === "run.dequeued")
          runStatus = "running";
        if (event === "run.queued") runStatus = "queued";
        if (event === "run.finished") runStatus = text(data.status);
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
        if (event === "node.confirm_request") {
          const requestId = text(data.request_id);
          if (
            requestId &&
            !pendingConfirmations.some(
              (request) => request.request_id === requestId,
            )
          ) {
            pendingConfirmations = [
              ...pendingConfirmations,
              {
                request_id: requestId,
                run_id: eventRunId || state.runId,
                node_id: nodeId,
                tool: text(data.tool),
                args: record(data.args),
                timeout_at: text(data.timeout_at) || undefined,
              },
            ];
          }
        }
        if (event === "node.confirm_resolved")
          pendingConfirmations = pendingConfirmations.filter(
            (request) => request.request_id !== text(data.request_id),
          );
        return {
          runStatus,
          statuses,
          errors,
          logs,
          iterations,
          traces,
          pendingConfirmations,
        };
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
    baseline: (baseline, entries) => {
      if (!baseline) {
        set(emptyRun());
        return;
      }
      const statuses = Object.fromEntries(
        Object.entries(baseline.nodes).map(([id, node]) => [id, node.status]),
      );
      const errors = Object.fromEntries(
        Object.entries(baseline.nodes).flatMap(([id, node]) =>
          node.error ? [[id, node.error]] : [],
        ),
      );
      const logs: LogEntry[] = [];
      const iterations: RunState["iterations"] = {};
      const traces: RunState["traces"] = {};
      const pending = new Map<string, ConfirmRequest>();
      for (const entry of entries) {
        const data = record(entry.data);
        const nodeId = text(entry.node_id) || eventNodeId(data);
        if (entry.event === "node.log")
          logs.push({
            node_id: nodeId,
            level: text(data.level, "INFO"),
            message: text(data.message),
          });
        if (entry.event === "node.iteration")
          iterations[nodeId] = {
            index: Number(data.index),
            total: Number(data.total),
          };
        if (entry.event === "node.stream")
          traces[nodeId] = [
            ...(traces[nodeId] ?? []),
            { type: "stream", ...data },
          ];
        if (entry.event === "node.tool_call")
          traces[nodeId] = [
            ...(traces[nodeId] ?? []),
            { type: "tool", ...data },
          ];
        if (entry.event === "node.llm_trace")
          traces[nodeId] = [
            ...(traces[nodeId] ?? []),
            { type: "llm", ...data },
          ];
        if (entry.event === "node.confirm_request") {
          const requestId = text(data.request_id);
          if (requestId)
            pending.set(requestId, {
              request_id: requestId,
              run_id: baseline.run_id,
              node_id: nodeId,
              tool: text(data.tool),
              args: record(data.args),
              timeout_at: text(data.timeout_at) || undefined,
            });
        }
        if (entry.event === "node.confirm_resolved")
          pending.delete(text(data.request_id));
      }
      set({
        ...emptyRun(baseline.run_id, baseline.status),
        statuses,
        errors,
        logs,
        iterations,
        traces,
        pendingConfirmations: [...pending.values()],
      });
    },
    reset: () => {
      set(emptyRun());
    },
  })),
);
