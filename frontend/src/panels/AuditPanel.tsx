import { useEffect, useState } from "react";
import { api } from "../api/client";

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
    <section aria-label="审计历史">
      <button
        onClick={() => {
          setOpen(!open);
        }}
      >
        审计
      </button>
      {open && (
        <div>
          <input
            aria-label="按工具筛选"
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
          <ul>
            {filtered.map((entry, index) => (
              <li key={index}>
                {entry.tool} / {entry.status} / {entry.duration_ms} ms
                <pre>{JSON.stringify(entry.args_redacted)}</pre>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
