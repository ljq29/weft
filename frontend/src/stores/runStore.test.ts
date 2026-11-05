import { beforeEach, describe, expect, it } from "vitest";
import { useRunStore } from "./runStore";

describe("T2.3 execution visualization", () => {
  beforeEach(() => {
    useRunStore.getState().reset();
  });

  it("US-DES-05/AC-1,2, US-EXE-05/AC-4: applies node status, errors and grouped logs", () => {
    useRunStore.getState().started("r_1");
    useRunStore
      .getState()
      .apply({ event: "node.started", data: { node_id: "n_1" } });
    expect(useRunStore.getState().statuses.n_1).toBe("running");
    useRunStore.getState().apply({
      event: "node.finished",
      data: { node_id: "n_1", from_cache: true },
    });
    expect(useRunStore.getState().statuses.n_1).toBe("executed");
    useRunStore.getState().apply({
      event: "node.log",
      data: { node_id: "n_1", level: "INFO", message: "done" },
    });
    expect(useRunStore.getState().logs).toEqual([
      { node_id: "n_1", level: "INFO", message: "done" },
    ]);
  });

  it("US-EXE-07/AC-2: stores readable error details for the failed node", () => {
    useRunStore.getState().apply({
      event: "node.failed",
      data: {
        node_id: "n_2",
        error: { message: "bad column", traceback: "trace" },
      },
    });
    expect(useRunStore.getState().statuses.n_2).toBe("failed");
    expect(useRunStore.getState().errors.n_2.traceback).toBe("trace");
  });

  it("US-EXE-05/AC-3: restores final node state from a REST snapshot after reconnect", () => {
    useRunStore.getState().snapshot({ nodes: { n_1: { status: "executed" } } });
    expect(useRunStore.getState().statuses.n_1).toBe("executed");
  });

  it("US-EXE-05/AC-3, US-AGT-12/AC-2: restores logs and unresolved confirmations from a run baseline", () => {
    useRunStore.getState().baseline(
      {
        run_id: "r_2",
        status: "waiting",
        nodes: { n_1: { status: "running" } },
      },
      [
        {
          event: "node.log",
          node_id: "n_1",
          data: { level: "WARN", message: "check" },
        },
        {
          event: "node.confirm_request",
          node_id: "n_1",
          data: {
            request_id: "request_1",
            run_id: "r_2",
            tool: "write",
            args: { path: "out.txt" },
          },
        },
        {
          event: "node.confirm_request",
          node_id: "n_1",
          data: {
            request_id: "request_2",
            run_id: "r_2",
            tool: "edit",
            args: {},
          },
        },
        {
          event: "node.confirm_resolved",
          node_id: "n_1",
          data: { request_id: "request_1" },
        },
      ],
    );
    const state = useRunStore.getState();
    expect(state.runId).toBe("r_2");
    expect(state.runStatus).toBe("waiting");
    expect(state.logs).toEqual([
      { node_id: "n_1", level: "WARN", message: "check" },
    ]);
    expect(state.pendingConfirmations.map((item) => item.request_id)).toEqual([
      "request_2",
    ]);
  });

  it("US-EXE-05/AC-3: ignores unknown events without changing run state", () => {
    const before = useRunStore.getState();
    useRunStore
      .getState()
      .apply({ event: "node.unknown", data: { node_id: "n_1" } });
    expect(useRunStore.getState()).toBe(before);
  });

  it("US-EXE-10/AC-3: records iteration progress for the loop node", () => {
    useRunStore.getState().apply({
      event: "node.iteration",
      data: { node_id: "n_loop", index: 3, total: 10 },
    });
    expect(useRunStore.getState().iterations.n_loop).toEqual({
      index: 3,
      total: 10,
    });
  });

  it("US-AGT-03/AC-5; US-AGT-10/AC-1,2: stores LLM and tool timeline events", () => {
    useRunStore.getState().apply({
      event: "node.llm_trace",
      data: {
        node_id: "n_agent",
        turn: 1,
        prompt_tokens: 3,
        completion_tokens: 1,
        latency_ms: 20,
      },
    });
    useRunStore.getState().apply({
      event: "node.tool_call",
      data: { node_id: "n_agent", tool: "lookup", duration_ms: 5 },
    });
    expect(useRunStore.getState().traces.n_agent).toHaveLength(2);
    expect(useRunStore.getState().traces.n_agent[0].prompt_tokens).toBe(3);
  });
});
