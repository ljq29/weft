import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Icon } from "../components/Icon";

interface AuditEntry {
  tool: string;
  status: string;
  duration_ms: number;
  args_redacted: unknown;
}

export function AuditPanel({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [tool, setTool] = useState("");
  const [status, setStatus] = useState("");
  useEffect(() => {
    if (!open || !runId) return;
    void api<AuditEntry[]>(`/runs/${runId}/audit`)
      .then((entries) => {
        setEntries(entries);
      })
      .catch(() => {
        setEntries([]);
      });
  }, [open, runId]);
  const filtered = entries.filter(
    (entry) =>
      entry.tool.includes(tool) && (!status || entry.status === status),
  );
  return (
    <section className="inspector-section" aria-label="审计历史">
      <button
        className="section-toggle"
        onClick={() => {
          setOpen(!open);
        }}
      >
        <span>
          <Icon name="shield" />
          审计
        </span>
        <Icon name="down" className={open ? "rotated" : ""} />
      </button>
      {open && (
        <div className="section-content">
          <div className="filter-row">
            <input
              aria-label="按工具筛选"
              placeholder="工具名称"
              value={tool}
              onChange={(event) => {
                setTool(event.target.value);
              }}
            />
            <select
              aria-label="按状态筛选"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
              }}
            >
              <option value="">全部状态</option>
              <option value="ok">ok</option>
              <option value="error">error</option>
              <option value="rejected">rejected</option>
            </select>
          </div>
          <ul className="audit-list">
            {filtered.map((entry, index) => (
              <li key={index}>
                <div>
                  <strong>{entry.tool}</strong>
                  <span className={`tag ${entry.status}`}>{entry.status}</span>
                  <small>{entry.duration_ms} ms</small>
                </div>
                <pre>{JSON.stringify(entry.args_redacted)}</pre>
              </li>
            ))}
            {filtered.length === 0 && (
              <li className="section-empty">暂无审计记录</li>
            )}
          </ul>
        </div>
      )}
    </section>
  );
}
