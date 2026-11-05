import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Icon } from "../components/Icon";

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
    <section
      className={`history-panel${open ? " open" : ""}`}
      aria-label="运行历史"
    >
      <header className="bottom-panel-header">
        <button
          className="history-toggle"
          onClick={() => {
            setOpen(!open);
          }}
        >
          <Icon name="history" />
          <span>历史</span>
          <Icon name="down" className={open ? "rotated" : ""} />
        </button>
        {open && (
          <span className="panel-caption">最近 20 次运行 · 只读快照</span>
        )}
      </header>
      {open && (
        <div className="history-layout">
          <div className="run-list">
            {runs.map((run) => (
              <button
                className={
                  detail?.run_id === run.run_id
                    ? "run-item selected"
                    : "run-item"
                }
                key={run.run_id}
                onClick={() => void select(run.run_id)}
              >
                <span className={`status-dot ${run.status}`} />
                <span>
                  <strong>{run.run_id}</strong>
                  <small>
                    {" · "}
                    {run.trigger_source} · {run.status}
                  </small>
                </span>
                <Icon name="chevron" />
              </button>
            ))}
            {runs.length === 0 && (
              <div className="bottom-empty">暂无运行记录</div>
            )}
          </div>
          {detail && (
            <section className="history-detail" aria-label="历史运行详情">
              <header>
                <div>
                  <span className={`tag ${detail.status}`}>
                    {detail.status}
                  </span>
                  <h3>{detail.run_id}</h3>
                </div>
                <span>{detail.trigger.source} 触发</span>
              </header>
              <div className="table-scroll">
                <table className="data-table">
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
                        <td>
                          <span className={`tag ${node.status}`}>
                            {node.status}
                          </span>
                        </td>
                        <td>{node.from_cache ? "是" : "否"}</td>
                        <td className="table-actions">
                          <button
                            className="text-button"
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
                              className="text-button"
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
              </div>
              {Object.entries(detail.nodes).map(([nodeId, node]) =>
                node.error ? (
                  <pre className="error-details" key={nodeId}>
                    {nodeId}: {node.error.traceback ?? node.error.message}
                  </pre>
                ) : null,
              )}
              <div className="history-lower">
                <section>
                  <h4>历史日志</h4>
                  {logs.map((entry, index) => (
                    <p className="history-log" key={index}>
                      <strong>{entry.event}</strong> {entry.node_id}{" "}
                      {typeof entry.data.message === "string"
                        ? entry.data.message
                        : JSON.stringify(entry.data.message ?? "")}
                    </p>
                  ))}
                </section>
                {traceNode && (
                  <section>
                    <h4>{traceNode} 轨迹</h4>
                    <pre>{JSON.stringify(traces, null, 2)}</pre>
                  </section>
                )}
              </div>
            </section>
          )}
        </div>
      )}
    </section>
  );
}
