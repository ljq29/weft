import { api, sessionToken } from "./client";
import {
  useConnectionStore,
  setReconnectHandler,
  type ConnectionStatus,
} from "../stores/connectionStore";
import {
  useRunStore,
  type RunBaseline,
  type RunEvent,
  type RunLogEntry,
} from "../stores/runStore";

interface RunSummary {
  run_id: string;
  status: string;
}
interface Message {
  topic: string;
  event: string;
  ts?: string;
  data: Record<string, unknown>;
}
interface ActiveConnection {
  stop: () => void;
  reconnect: () => void;
}
interface SubscriptionAck {
  socket: WebSocket;
  topics: string[];
  resolve: () => void;
  reject: (reason: Error) => void;
}

const activeRunStatuses = new Set(["queued", "running", "waiting"]);
const runEvents = new Set([
  "run.started",
  "run.queued",
  "run.dequeued",
  "run.finished",
  "run.warning",
  "node.started",
  "node.status",
  "node.finished",
  "node.failed",
  "node.progress",
  "node.log",
  "node.stream",
  "node.tool_call",
  "node.llm_trace",
  "node.iteration",
  "node.confirm_request",
  "node.confirm_resolved",
  "chat.message",
  "changes.ready",
]);
const workflowEvents = new Set([
  "run.started",
  "run.queued",
  "run.dequeued",
  "run.finished",
  "workflow.saved",
  "env.progress",
  "pack.finished",
  "pack.failed",
  "trigger.status",
]);

let activeConnection: ActiveConnection | null = null;

function object(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function parseMessage(value: unknown): Message | null {
  const parsed: unknown = JSON.parse(String(value));
  const envelope = object(parsed);
  if (!envelope) return null;
  const data = object(envelope.data) ?? {};
  if (typeof envelope.topic !== "string" || typeof envelope.event !== "string")
    return null;
  return {
    topic: envelope.topic,
    event: envelope.event,
    ts: typeof envelope.ts === "string" ? envelope.ts : undefined,
    data,
  };
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

function logSignature(entry: RunLogEntry | Message): string {
  if (!entry.ts) return "";
  const data = { ...entry.data };
  delete data.run_id;
  delete data.node_id;
  const nodeId =
    "node_id" in entry && typeof entry.node_id === "string"
      ? entry.node_id
      : typeof entry.data.node_id === "string"
        ? entry.data.node_id
        : "";
  return JSON.stringify([entry.event, nodeId, entry.ts, data]);
}

export function connectRuns(workflowId: string): () => void {
  activeConnection?.stop();

  let stopped = false;
  let phase: ConnectionStatus = "idle";
  let socket: WebSocket | null = null;
  let retryTimer: number | null = null;
  let handshakeTimer: number | null = null;
  let subscriptionAck: SubscriptionAck | null = null;
  let attempt = 0;
  let pendingEvents: Message[] = [];
  const subscribedTopics = new Set<string>();

  const isActive = () => activeConnection === controller && !stopped;
  const isCurrent = (candidate: WebSocket) =>
    isActive() && socket === candidate;

  function updateStore(
    status: ConnectionStatus,
    values: Partial<{
      attempt: number;
      retryAt: number | null;
      error: string;
    }> = {},
  ) {
    if (!isActive()) return;
    phase = status;
    if (status === "ready") attempt = 0;
    useConnectionStore.setState({
      status,
      workflowId,
      attempt,
      retryAt: null,
      error: "",
      ...values,
    });
  }

  function clearHandshake() {
    if (handshakeTimer !== null) window.clearTimeout(handshakeTimer);
    handshakeTimer = null;
  }

  function rejectSubscription(reason: Error) {
    const pending = subscriptionAck;
    subscriptionAck = null;
    pending?.reject(reason);
  }

  function detach(candidate: WebSocket) {
    candidate.onopen = null;
    candidate.onmessage = null;
    candidate.onerror = null;
    candidate.onclose = null;
    if (socket === candidate) socket = null;
    clearHandshake();
    rejectSubscription(new Error("连接已关闭"));
  }

  function scheduleBackoff() {
    if (!isActive()) return;
    updateStore("disconnected");
    if (!navigator.onLine) return;
    attempt += 1;
    const ceiling = Math.min(30_000, 500 * 2 ** Math.min(attempt - 1, 8));
    const delay = Math.round(ceiling * (0.5 + Math.random()));
    const retryAt = Date.now() + delay;
    updateStore("backoff", { attempt, retryAt });
    retryTimer = window.setTimeout(open, delay);
  }

  function fail(candidate: WebSocket, reason: unknown) {
    if (!isCurrent(candidate)) return;
    const message = errorMessage(reason);
    detach(candidate);
    candidate.close();
    updateStore("disconnected", { error: message });
    scheduleBackoff();
  }

  function knownEvent(message: Message): boolean {
    if (message.topic === `workflow:${workflowId}`)
      return workflowEvents.has(message.event);
    if (!message.topic.startsWith("run:")) return false;
    return (
      runEvents.has(message.event) &&
      message.data.run_id === message.topic.slice(4)
    );
  }

  function dispatch(message: Message) {
    if (
      message.topic.startsWith("run:") &&
      message.event !== "run.started" &&
      message.event !== "run.queued"
    ) {
      const currentRunId = useRunStore.getState().runId;
      if (currentRunId && message.data.run_id !== currentRunId) return;
    }
    const event: RunEvent = { event: message.event, data: message.data };
    useRunStore.getState().apply(event);
    window.dispatchEvent(new CustomEvent("weft-chat", { detail: message }));
  }

  function flushEvents(baselineEntries: RunLogEntry[] = []) {
    const baseline = new Set(
      baselineEntries.map(logSignature).filter((signature) => signature),
    );
    const queued = pendingEvents;
    pendingEvents = [];
    for (const message of queued) {
      const signature = logSignature(message);
      if (signature && baseline.has(signature)) continue;
      dispatch(message);
    }
  }

  function subscribe(candidate: WebSocket, topics: string[]): Promise<void> {
    if (!isCurrent(candidate) || candidate.readyState !== WebSocket.OPEN)
      return Promise.reject(new Error("WebSocket 尚未连接"));
    updateStore("subscribing");
    return new Promise((resolve, reject) => {
      subscriptionAck = { socket: candidate, topics, resolve, reject };
      clearHandshake();
      handshakeTimer = window.setTimeout(() => {
        rejectSubscription(new Error("订阅确认超时"));
        if (isCurrent(candidate)) fail(candidate, "订阅确认超时");
      }, 10_000);
      candidate.send(JSON.stringify({ op: "subscribe", topics }));
    });
  }

  async function synchronizeRun(candidate: WebSocket) {
    const runId = useRunStore.getState().runId;
    const topic = runId ? `run:${runId}` : "";
    if (!topic || subscribedTopics.has(topic)) {
      if (isCurrent(candidate)) {
        updateStore("ready", { attempt: 0 });
        flushEvents();
      }
      return;
    }
    await subscribe(candidate, [topic]);
    if (!isCurrent(candidate)) return;
    subscribedTopics.add(topic);
    if (useRunStore.getState().runId !== runId) {
      await synchronizeRun(candidate);
      return;
    }
    updateStore("ready", { attempt: 0 });
    flushEvents();
  }

  async function restoreBaseline(candidate: WebSocket) {
    const observedRunId = useRunStore.getState().runId;
    const runs = await api<RunSummary[]>(
      `/workflows/${workflowId}/runs?limit=20`,
    );
    if (!isCurrent(candidate)) return;
    const selected =
      runs.find((run) => run.run_id === observedRunId) ??
      runs.find((run) => activeRunStatuses.has(run.status)) ??
      (runs.length > 0 ? runs[0] : undefined);
    if (!selected) {
      if (observedRunId !== useRunStore.getState().runId) {
        await restoreBaseline(candidate);
        return;
      }
      useRunStore.getState().baseline(null, []);
      updateStore("ready", { attempt: 0 });
      flushEvents();
      return;
    }
    const topic = `run:${selected.run_id}`;
    if (!subscribedTopics.has(topic)) {
      await subscribe(candidate, [topic]);
      if (!isCurrent(candidate)) return;
      subscribedTopics.add(topic);
    }
    const [record, entries] = await Promise.all([
      api<RunBaseline>(`/runs/${selected.run_id}`),
      api<RunLogEntry[]>(`/runs/${selected.run_id}/log`),
    ]);
    if (!isCurrent(candidate)) return;
    if (record.workflow_id && record.workflow_id !== workflowId)
      throw new Error("运行记录不属于当前工作流");
    if (observedRunId !== useRunStore.getState().runId) {
      await restoreBaseline(candidate);
      return;
    }
    useRunStore.getState().baseline(record, entries);
    updateStore("ready", { attempt: 0 });
    for (const request of useRunStore.getState().pendingConfirmations) {
      window.dispatchEvent(
        new CustomEvent("weft-chat", {
          detail: {
            topic,
            event: "node.confirm_request",
            data: { ...request },
          },
        }),
      );
    }
    flushEvents(entries);
  }

  async function recover(candidate: WebSocket) {
    const topic = `workflow:${workflowId}`;
    await subscribe(candidate, [topic]);
    if (!isCurrent(candidate)) return;
    subscribedTopics.add(topic);
    await restoreBaseline(candidate);
  }

  function onMessage(candidate: WebSocket, event: MessageEvent) {
    if (!isCurrent(candidate)) return;
    let message: Message;
    try {
      const parsed = parseMessage(event.data);
      if (!parsed) return;
      message = parsed;
    } catch {
      return;
    }
    if (message.topic !== "system") {
      if (
        (phase === "ready" || phase === "subscribing") &&
        knownEvent(message)
      ) {
        if (phase === "ready") dispatch(message);
        else pendingEvents.push(message);
      }
      return;
    }
    if (message.event === "authenticated") {
      if (phase !== "authenticating") return;
      clearHandshake();
      void recover(candidate).catch((reason: unknown) => {
        fail(candidate, reason);
      });
      return;
    }
    if (message.event === "subscribed") {
      const pending = subscriptionAck;
      if (!pending || pending.socket !== candidate) return;
      const topics = Array.isArray(message.data.topics)
        ? message.data.topics
        : [];
      if (!pending.topics.every((topic) => topics.includes(topic))) return;
      clearHandshake();
      subscriptionAck = null;
      pending.resolve();
    }
  }

  function open() {
    retryTimer = null;
    if (!isActive()) return;
    if (!navigator.onLine) {
      updateStore("disconnected", { error: "浏览器当前离线" });
      return;
    }
    updateStore("connecting", { error: "" });
    let candidate: WebSocket;
    try {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      candidate = new WebSocket(`${protocol}://${window.location.host}/api/ws`);
    } catch (reason) {
      useConnectionStore.setState({ error: errorMessage(reason) });
      scheduleBackoff();
      return;
    }
    socket = candidate;
    subscribedTopics.clear();
    pendingEvents = [];
    candidate.onopen = () => {
      if (!isCurrent(candidate)) return;
      updateStore("authenticating", { error: "" });
      clearHandshake();
      handshakeTimer = window.setTimeout(() => {
        fail(candidate, "认证确认超时");
      }, 10_000);
      try {
        candidate.send(
          JSON.stringify({ op: "authenticate", token: sessionToken() }),
        );
      } catch (reason) {
        fail(candidate, reason);
      }
    };
    candidate.onmessage = (event) => {
      onMessage(candidate, event);
    };
    candidate.onerror = () => {
      fail(candidate, "WebSocket 连接错误");
    };
    candidate.onclose = () => {
      if (!isCurrent(candidate)) return;
      detach(candidate);
      scheduleBackoff();
    };
  }

  function reconnect() {
    if (!isActive()) return;
    if (retryTimer !== null) window.clearTimeout(retryTimer);
    retryTimer = null;
    const previous = socket;
    if (previous) {
      detach(previous);
      previous.close();
    }
    open();
  }

  function onOnline() {
    reconnect();
  }

  function onOffline() {
    if (!isActive()) return;
    if (retryTimer !== null) window.clearTimeout(retryTimer);
    retryTimer = null;
    const previous = socket;
    if (previous) {
      detach(previous);
      previous.close();
    }
    updateStore("disconnected", {
      retryAt: null,
      error: "浏览器当前离线",
    });
  }

  const controller: ActiveConnection = {
    stop: () => {
      if (stopped) return;
      stopped = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      retryTimer = null;
      unsubscribeRun();
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      const previous = socket;
      if (previous) {
        detach(previous);
        previous.close();
      }
      if (activeConnection === controller) {
        activeConnection = null;
        setReconnectHandler(null);
        useConnectionStore.setState({
          status: "idle",
          workflowId: "",
          attempt: 0,
          retryAt: null,
          error: "",
        });
      }
    },
    reconnect,
  };

  const unsubscribeRun = useRunStore.subscribe(
    (state) => state.runId,
    () => {
      const current = socket;
      if (isActive() && phase === "ready" && current)
        void synchronizeRun(current).catch((reason: unknown) => {
          fail(current, reason);
        });
    },
  );

  activeConnection = controller;
  setReconnectHandler(reconnect);
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
  open();
  return controller.stop;
}
