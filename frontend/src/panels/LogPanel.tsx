import { useState } from "react";
import { useRunStore } from "../stores/runStore";
import { useWorkflowStore } from "../stores/workflowStore";
import { Icon } from "../components/Icon";
import type { RunValueRef } from "../stores/runStore";

function outputSummary(reference: RunValueRef): string {
  if (reference.kind === "table")
    return `Table · ${String(reference.rows ?? "?")} 行 × ${String(reference.cols ?? "?")} 列`;
  if (reference.kind === "json") return "JSON";
  return "无值";
}

export function LogPanel({
  onPreview,
}: {
  onPreview: (nodeId: string, port: string) => void;
}) {
  const logs = useRunStore((state) => state.logs);
  const outputs = useRunStore((state) => state.outputs);
  const runId = useRunStore((state) => state.runId);
  const runStatus = useRunStore((state) => state.runStatus);
  const nodes = useWorkflowStore((state) => state.nodes);
  const [level, setLevel] = useState("");
  const [node, setNode] = useState("");
  const [view, setView] = useState<"logs" | "outputs">("logs");
  const filtered = logs.filter(
    (entry) =>
      (!level || entry.level === level) && (!node || entry.node_id === node),
  );
  const outputRows = Object.entries(outputs).flatMap(([nodeId, ports]) =>
    Object.entries(ports).map(([port, reference]) => ({
      nodeId,
      port,
      reference,
      name: nodes.find((item) => item.id === nodeId)?.data.name ?? nodeId,
    })),
  );
  return (
    <section className="log-panel" aria-label="执行日志">
      <header className="bottom-panel-header">
        <div className="bottom-panel-title">
          <Icon name="terminal" />
          <h2>当前运行</h2>
          <span>{runStatus || "未运行"}</span>
          <div className="run-view-tabs" aria-label="运行内容">
            <button
              aria-pressed={view === "logs"}
              onClick={() => {
                setView("logs");
              }}
            >
              日志 {filtered.length}
            </button>
            <button
              aria-pressed={view === "outputs"}
              onClick={() => {
                setView("outputs");
              }}
            >
              输出 {outputRows.length}
            </button>
          </div>
        </div>
        {view === "logs" ? (
          <div className="log-filters">
            <select
              aria-label="日志级别"
              value={level}
              onChange={(event) => {
                setLevel(event.target.value);
              }}
            >
              <option value="">全部级别</option>
              <option>INFO</option>
              <option>WARN</option>
              <option>ERROR</option>
            </select>
            <div className="compact-input">
              <Icon name="search" />
              <input
                aria-label="按节点过滤"
                placeholder="节点 ID"
                value={node}
                onChange={(event) => {
                  setNode(event.target.value);
                }}
              />
            </div>
          </div>
        ) : (
          <span className="panel-caption">{runId || "运行后可查看输出"}</span>
        )}
      </header>
      {view === "logs" ? (
        <div className="log-list">
          {filtered.map((entry, index) => (
            <p className="log-entry" data-level={entry.level} key={index}>
              <strong className={`log-level ${entry.level.toLowerCase()}`}>
                {entry.level}
              </strong>
              <span className="log-node">{entry.node_id}</span>
              <span className="log-message">{entry.message}</span>
            </p>
          ))}
          {filtered.length === 0 && (
            <div className="bottom-empty">暂无匹配日志</div>
          )}
        </div>
      ) : (
        <div className="run-output-list" aria-label="当前运行输出">
          {outputRows.map(({ nodeId, port, reference, name }) => (
            <button
              className="run-output-item"
              key={`${nodeId}:${port}`}
              onClick={() => {
                onPreview(nodeId, port);
              }}
            >
              <span>
                <strong>{name}</strong>
                <small>{nodeId}</small>
              </span>
              <span className="run-output-port">{port}</span>
              <span className="run-output-kind">
                {outputSummary(reference)}
              </span>
              <Icon name="chevron" />
            </button>
          ))}
          {outputRows.length === 0 && (
            <div className="bottom-empty">当前 Run 暂无可预览输出</div>
          )}
        </div>
      )}
    </section>
  );
}
