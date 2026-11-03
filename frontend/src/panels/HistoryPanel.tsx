import { useEffect, useState } from "react";
import { api } from "../api/client";

interface RunSummary {
  run_id: string;
  trigger_source: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
}
interface RunDetail {
  run_id: string;
  status: string;
  trigger: { source: string };
  nodes: Record<
    string,
    {
      status: string;
      from_cache: boolean;
      error?: { message: string; traceback?: string };
      outputs: Record<string, unknown>;
    }
  >;
}
interface LogEntry {
  event: string;
  node_id: string;
  data: Record<string, unknown>;
}

export function HistoryPanel({
  workflowId,
  onPreview,
}: {
  workflowId: string;
  onPreview: (runId: string, nodeId: string, port: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [traces, setTraces] = useState<unknown[]>([]);
  const [traceNode, setTraceNode] = useState("");
  useEffect(() => {
    if (!open || !workflowId) return;
    void api<RunSummary[]>(`/workflows/${workflowId}/runs?limit=20`)
      .then(setRuns)
      .catch(() => {
        setRuns([]);
      });
  }, [open, workflowId]);
  const select = async (runId: string) => {
    const [record, entries] = await Promise.all([
      api<RunDetail>(`/runs/${runId}`),
      api<LogEntry[]>(`/runs/${runId}/log`),
    ]);
    setDetail(record);
    setLogs(entries);
    setTraces([]);
    setTraceNode("");
  };
  return (
    <section className="history-panel" aria-label="运行历史">
      <button
        onClick={() => {
          setOpen(!open);
        }}
      >
        历史
      </button>
      {open && (
        <div>
          {runs.map((run) => (
            <button key={run.run_id} onClick={() => void select(run.run_id)}>
              {run.run_id} · {run.trigger_source} · {run.status}
            </button>
          ))}
          {detail && (
            <section aria-label="历史运行详情">
              <h3>
                {detail.run_id} · {detail.status}
              </h3>
              <table>
                <thead>
                  <tr>
                    <th>节点</th>
                    <th>状态</th>
                    <th>缓存</th>
                    <th>只读操作</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(detail.nodes).map(([nodeId, node]) => (
                    <tr key={nodeId}>
                      <td>{nodeId}</td>
                      <td>{node.status}</td>
                      <td>{node.from_cache ? "是" : "否"}</td>
                      <td>
                        <button
                          onClick={() => {
                            setTraceNode(nodeId);
                            void api<unknown[]>(
                              `/runs/${detail.run_id}/nodes/${nodeId}/trace`,
                            ).then(setTraces);
                          }}
                        >
                          查看轨迹
                        </button>
                        {Object.keys(node.outputs).map((port) => (
                          <button
                            key={port}
                            onClick={() => {
                              onPreview(detail.run_id, nodeId, port);
                            }}
                          >
                            查看 {port}
                          </button>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {Object.entries(detail.nodes).map(([nodeId, node]) =>
                node.error ? (
                  <pre key={nodeId}>
                    {nodeId}: {node.error.traceback ?? node.error.message}
                  </pre>
                ) : null,
              )}
              <h4>历史日志</h4>
              {logs.map((entry, index) => (
                <p key={index}>
                  {entry.event} {entry.node_id}{" "}
                  {typeof entry.data.message === "string"
                    ? entry.data.message
                    : JSON.stringify(entry.data.message ?? "")}
                </p>
              ))}
              {traceNode && <h4>{traceNode} 轨迹</h4>}
              {traceNode && <pre>{JSON.stringify(traces, null, 2)}</pre>}
            </section>
          )}
        </div>
      )}
    </section>
  );
}
