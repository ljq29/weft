import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { connectRuns } from "./ws";
import { api } from "./client";
import { useConnectionStore } from "../stores/connectionStore";
import { useRunStore } from "../stores/runStore";
import { useWorkflowStore } from "../stores/workflowStore";

vi.mock("./client", () => ({
  api: vi.fn(),
  sessionToken: vi.fn(() => "session-token"),
}));

type SocketMessage = Record<string, unknown>;

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;
  readonly url: string;
  readonly sent: SocketMessage[] = [];
  readyState = FakeWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(value: string) {
    if (this.readyState !== FakeWebSocket.OPEN)
      throw new Error("socket is not open");
    this.sent.push(JSON.parse(value) as SocketMessage);
  }

  close() {
    if (this.readyState === FakeWebSocket.CLOSED) return;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.(new Event("close"));
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  message(message: SocketMessage) {
    const event = new Event("message") as MessageEvent;
    Object.defineProperty(event, "data", {
      value: typeof message === "string" ? message : JSON.stringify(message),
    });
    this.onmessage?.(event);
  }

  authenticate() {
    this.open();
    this.message({ topic: "system", event: "authenticated", data: {} });
  }

  acknowledge(topics: string[]) {
    this.message({
      topic: "system",
      event: "subscribed",
      data: { topics },
    });
  }
}

const apiMock = vi.mocked(api);
const cleanups: (() => void)[] = [];

function connect(workflowId = "wf_1") {
  const cleanup = connectRuns(workflowId);
  cleanups.push(cleanup);
  const socket = FakeWebSocket.instances.at(-1);
  if (!socket) throw new Error("WebSocket was not created");
  return socket;
}

async function readyWithoutRuns(socket: FakeWebSocket, workflowId = "wf_1") {
  socket.authenticate();
  socket.acknowledge([`workflow:${workflowId}`]);
  await vi.waitFor(() => {
    expect(useConnectionStore.getState().status).toBe("ready");
  });
}

describe("reliable workflow WebSocket", () => {
  beforeEach(() => {
    const target = new EventTarget();
    vi.stubGlobal(
      "window",
      Object.assign(target, {
        location: { protocol: "https:", host: "weft.local" },
        setTimeout: globalThis.setTimeout,
        clearTimeout: globalThis.clearTimeout,
      }),
    );
    vi.stubGlobal("navigator", { onLine: true });
    vi.stubGlobal("WebSocket", FakeWebSocket);
    FakeWebSocket.instances = [];
    apiMock.mockReset();
    apiMock.mockResolvedValue([] as never);
    useRunStore.getState().reset();
    useConnectionStore.setState({
      status: "idle",
      workflowId: "",
      attempt: 0,
      retryAt: null,
      error: "",
    });
  });

  afterEach(() => {
    while (cleanups.length) cleanups.pop()?.();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("US-EXE-05/AC-3,5: uses wss and waits for authentication ACK before subscribing", async () => {
    const socket = connect();
    expect(socket.url).toBe("wss://weft.local/api/ws");
    expect(useConnectionStore.getState().status).toBe("connecting");
    socket.open();
    expect(socket.sent).toEqual([
      { op: "authenticate", token: "session-token" },
    ]);
    expect(useConnectionStore.getState().status).toBe("authenticating");
    socket.message({
      topic: "run:r_1",
      event: "node.status",
      data: { run_id: "r_1", node_id: "n_1", status: "failed" },
    });
    expect(useRunStore.getState().statuses).toEqual({});
    socket.message({ topic: "system", event: "authenticated", data: {} });
    expect(socket.sent).toHaveLength(2);
    expect(socket.sent[1]).toEqual({
      op: "subscribe",
      topics: ["workflow:wf_1"],
    });
    expect(useConnectionStore.getState().status).toBe("subscribing");
    socket.acknowledge(["workflow:wf_1"]);
    await vi.waitFor(() => {
      expect(useConnectionStore.getState().status).toBe("ready");
    });
  });

  it("US-EXE-05/AC-3, US-AGT-12/AC-2: restores the current run baseline without touching dirty graph state", async () => {
    useRunStore.getState().started("r_1");
    useWorkflowStore.setState({ dirty: true });
    apiMock.mockImplementation((path) => {
      if (path === "/workflows/wf_1/runs?limit=20")
        return Promise.resolve([{ run_id: "r_1", status: "waiting" }]);
      if (path === "/runs/r_1")
        return Promise.resolve({
          run_id: "r_1",
          workflow_id: "wf_1",
          status: "waiting",
          nodes: { n_1: { status: "running" } },
        });
      if (path === "/runs/r_1/log")
        return Promise.resolve([
          {
            event: "node.log",
            node_id: "n_1",
            ts: "t1",
            data: { level: "INFO", message: "restored" },
          },
          {
            event: "node.confirm_request",
            node_id: "n_1",
            ts: "t2",
            data: {
              request_id: "request_1",
              run_id: "r_1",
              tool: "write",
              args: { path: "out.txt" },
            },
          },
        ]);
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    const socket = connect();
    socket.authenticate();
    socket.acknowledge(["workflow:wf_1"]);
    await vi.waitFor(() => {
      expect(socket.sent.at(-1)).toEqual({
        op: "subscribe",
        topics: ["run:r_1"],
      });
    });
    socket.acknowledge(["workflow:wf_1", "run:r_1"]);
    await vi.waitFor(() => {
      expect(useConnectionStore.getState().status).toBe("ready");
    });
    const run = useRunStore.getState();
    expect(run.runId).toBe("r_1");
    expect(run.runStatus).toBe("waiting");
    expect(run.statuses).toEqual({ n_1: "running" });
    expect(run.logs).toEqual([
      { node_id: "n_1", level: "INFO", message: "restored" },
    ]);
    expect(run.pendingConfirmations).toHaveLength(1);
    expect(useWorkflowStore.getState().dirty).toBe(true);
  });

  it("US-EXE-05/AC-3: de-duplicates buffered events already present in the REST log", async () => {
    const deferredLog: { resolve: (value: unknown[]) => void } = {
      resolve: () => {
        throw new Error("log request has not started");
      },
    };
    apiMock.mockImplementation((path) => {
      if (path === "/workflows/wf_1/runs?limit=20")
        return Promise.resolve([{ run_id: "r_1", status: "running" }]);
      if (path === "/runs/r_1")
        return Promise.resolve({
          run_id: "r_1",
          workflow_id: "wf_1",
          status: "running",
          nodes: { n_1: { status: "running" } },
        });
      if (path === "/runs/r_1/log")
        return new Promise<never>((resolve) => {
          deferredLog.resolve = (value) => {
            resolve(value as never);
          };
        });
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    const socket = connect();
    socket.authenticate();
    socket.acknowledge(["workflow:wf_1"]);
    await vi.waitFor(() => {
      expect(socket.sent.at(-1)).toEqual({
        op: "subscribe",
        topics: ["run:r_1"],
      });
    });
    socket.acknowledge(["workflow:wf_1", "run:r_1"]);
    const pendingLog = deferredLog.resolve;
    await vi.waitFor(() => {
      expect(deferredLog.resolve).not.toBe(pendingLog);
    });
    socket.message({
      topic: "run:r_1",
      event: "node.log",
      ts: "t1",
      data: {
        run_id: "r_1",
        node_id: "n_1",
        level: "INFO",
        message: "once",
      },
    });
    deferredLog.resolve([
      {
        event: "node.log",
        node_id: "n_1",
        ts: "t1",
        data: { level: "INFO", message: "once" },
      },
    ]);
    await vi.waitFor(() => {
      expect(useConnectionStore.getState().status).toBe("ready");
    });
    expect(useRunStore.getState().logs).toHaveLength(1);
  });

  it("US-EXE-05/AC-3: ignores malformed and unknown topic/event combinations", async () => {
    const socket = connect();
    await readyWithoutRuns(socket);
    const before = useRunStore.getState();
    socket.message({
      topic: "workflow:wf_1",
      event: "node.status",
      data: { node_id: "n_1", status: "failed" },
    });
    socket.message({
      topic: "run:r_1",
      event: "node.unknown",
      data: { run_id: "r_1", node_id: "n_1" },
    });
    expect(useRunStore.getState()).toBe(before);
  });

  it("US-EXE-05/AC-3: applies exponential jittered backoff and handles offline/online", async () => {
    vi.useFakeTimers();
    window.setTimeout = globalThis.setTimeout;
    window.clearTimeout = globalThis.clearTimeout;
    vi.spyOn(Math, "random").mockReturnValue(0);
    const first = connect();
    first.open();
    first.close();
    expect(useConnectionStore.getState().status).toBe("backoff");
    expect(useConnectionStore.getState().retryAt).toBe(Date.now() + 250);
    await vi.advanceTimersByTimeAsync(249);
    expect(FakeWebSocket.instances).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances).toHaveLength(2);
    vi.stubGlobal("navigator", { onLine: false });
    window.dispatchEvent(new Event("offline"));
    expect(FakeWebSocket.instances[1].readyState).toBe(FakeWebSocket.CLOSED);
    expect(useConnectionStore.getState().status).toBe("disconnected");
    await vi.advanceTimersByTimeAsync(60_000);
    expect(FakeWebSocket.instances).toHaveLength(2);
    vi.stubGlobal("navigator", { onLine: true });
    window.dispatchEvent(new Event("online"));
    expect(FakeWebSocket.instances).toHaveLength(3);
    expect(useConnectionStore.getState().status).toBe("connecting");
  });

  it("US-EXE-05/AC-3: immediate reconnect and cleanup isolate stale socket events", async () => {
    const first = connect();
    first.open();
    useConnectionStore.getState().reconnect();
    const second = FakeWebSocket.instances[1];
    expect(first.readyState).toBe(FakeWebSocket.CLOSED);
    expect(useConnectionStore.getState().status).toBe("connecting");
    first.message({ topic: "system", event: "authenticated", data: {} });
    expect(useConnectionStore.getState().status).toBe("connecting");
    second.open();
    second.message({ topic: "system", event: "authenticated", data: {} });
    second.acknowledge(["workflow:wf_1"]);
    await Promise.resolve();
    cleanups.pop()?.();
    const before = useRunStore.getState();
    second.message({
      topic: "run:r_1",
      event: "node.failed",
      data: { run_id: "r_1", node_id: "n_1" },
    });
    second.close();
    expect(useRunStore.getState()).toBe(before);
    expect(useConnectionStore.getState().status).toBe("idle");
  });
});
