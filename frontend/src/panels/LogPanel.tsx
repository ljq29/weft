import { useState } from "react";
import { useRunStore } from "../stores/runStore";

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
      <input
        aria-label="按节点过滤"
        placeholder="节点 ID"
        value={node}
        onChange={(event) => {
          setNode(event.target.value);
        }}
      />
      <div>
        {filtered.map((entry, index) => (
          <p key={index}>
            <strong>
              {entry.level} {entry.node_id}
            </strong>{" "}
            {entry.message}
          </p>
        ))}
      </div>
    </section>
  );
}
