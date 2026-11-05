import { useEffect, useState } from "react";
import { api, formatApiError } from "../api/client";
import { Icon } from "../components/Icon";

interface ConfirmRequest {
  request_id: string;
  run_id: string;
  node_id: string;
  tool: string;
  args: Record<string, unknown>;
}

export function ConfirmPanel({ runId }: { runId: string }) {
  const [request, setRequest] = useState<ConfirmRequest | null>(null);
  const [args, setArgs] = useState("{}");
  const [error, setError] = useState("");
  useEffect(() => {
    const listener = (event: Event) => {
      const message = (
        event as CustomEvent<{
          event: string;
          data: Record<string, unknown>;
        }>
      ).detail;
      if (
        message.event === "node.confirm_request" &&
        message.data.run_id === runId
      ) {
        const request = message.data as unknown as ConfirmRequest;
        setRequest(request);
        setArgs(JSON.stringify(request.args, null, 2));
      }
      if (message.event === "node.confirm_resolved") setRequest(null);
    };
    window.addEventListener("weft-chat", listener);
    return () => {
      window.removeEventListener("weft-chat", listener);
    };
  }, [runId]);
  if (!request) return null;
  const decide = async (decision: "approve" | "reject") => {
    try {
      const modified = JSON.parse(args) as Record<string, unknown>;
      await api(`/runs/${runId}/confirm`, {
        method: "POST",
        body: JSON.stringify({
          request_id: request.request_id,
          decision,
          modified_args: modified,
        }),
      });
      setRequest(null);
    } catch (reason) {
      setError(formatApiError(reason));
    }
  };
  return (
    <div className="confirm-backdrop">
      <section
        role="alertdialog"
        aria-label="工具调用确认"
        className="confirm-card"
      >
        <header>
          <span className="dialog-icon warning">
            <Icon name="shield" />
          </span>
          <div>
            <h3>确认调用 {request.tool}</h3>
            <p>Agent 请求执行此工具，请核对参数后决定。</p>
          </div>
        </header>
        <label className="form-field">
          <span>调用参数（JSON）</span>
          <textarea
            aria-label="确认参数"
            value={args}
            onChange={(event) => {
              setArgs(event.target.value);
            }}
          />
        </label>
        <footer>
          <button
            className="button secondary"
            onClick={() => void decide("reject")}
          >
            <Icon name="close" />
            拒绝
          </button>
          <button
            className="button primary"
            onClick={() => void decide("approve")}
          >
            <Icon name="check" />
            批准
          </button>
        </footer>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
      </section>
    </div>
  );
}
