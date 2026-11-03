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
});
