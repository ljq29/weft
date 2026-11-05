import { useState } from "react";
import { useRunStore } from "../stores/runStore";
import { Icon } from "../components/Icon";

export function LogPanel() {
  const logs = useRunStore((state) => state.logs);
  const [level, setLevel] = useState("");
  const [node, setNode] = useState("");
  const filtered = logs.filter(
    (entry) =>
      (!level || entry.level === level) && (!node || entry.node_id === node),
  );
  return (
    <section className="log-panel" aria-label="执行日志">
      <header className="bottom-panel-header">
        <div className="bottom-panel-title">
          <Icon name="terminal" />
          <h2>运行日志</h2>
          <span>{filtered.length}</span>
        </div>
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
      </header>
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
    </section>
  );
}
