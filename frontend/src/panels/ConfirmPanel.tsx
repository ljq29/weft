import { useEffect, useState } from "react";
import { api } from "../api/client";

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
      setError(String(reason));
    }
  };
  return (
    <section
      role="alertdialog"
      aria-label="工具调用确认"
      className="confirm-card"
    >
      <h3>确认调用 {request.tool}</h3>
      <textarea
        aria-label="确认参数"
        value={args}
        onChange={(event) => {
          setArgs(event.target.value);
        }}
      />
      <button onClick={() => void decide("approve")}>批准</button>
      <button onClick={() => void decide("reject")}>拒绝</button>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
