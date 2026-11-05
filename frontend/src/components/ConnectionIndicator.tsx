import {
  useConnectionStore,
  type ConnectionStatus,
} from "../stores/connectionStore";

const labels: Record<ConnectionStatus, string> = {
  idle: "未连接",
  connecting: "正在连接",
  authenticating: "正在认证",
  subscribing: "正在同步",
  ready: "已连接",
  disconnected: "连接已断开",
  backoff: "等待重连",
};

interface ConnectionIndicatorViewProps {
  status: ConnectionStatus;
  attempt: number;
  error: string;
  reconnect: () => void;
}

export function ConnectionIndicatorView({
  status,
  attempt,
  error,
  reconnect,
}: ConnectionIndicatorViewProps) {
  return (
    <div
      className={`connection-indicator ${status}`}
      role="status"
      aria-label="连接状态"
      title={error || labels[status]}
    >
      <span className={`status-dot ${status}`} aria-hidden="true" />
      <span>
        {labels[status]}
        {status === "backoff" && attempt > 0
          ? `（第 ${attempt.toString()} 次）`
          : ""}
      </span>
      {status !== "idle" && status !== "ready" && (
        <button type="button" className="text-button" onClick={reconnect}>
          立即重连
        </button>
      )}
    </div>
  );
}

export function ConnectionIndicator() {
  const status = useConnectionStore((state) => state.status);
  const attempt = useConnectionStore((state) => state.attempt);
  const error = useConnectionStore((state) => state.error);
  const reconnect = useConnectionStore((state) => state.reconnect);
  return (
    <ConnectionIndicatorView
      status={status}
      attempt={attempt}
      error={error}
      reconnect={reconnect}
    />
  );
}
