import { useState } from "react";

export interface TraceEntry {
  type: string;
  [key: string]: unknown;
}

function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return value.toString();
  if (value === null || value === undefined) return "";
  const serialized: unknown = JSON.stringify(value);
  return typeof serialized === "string" ? serialized : "";
}

export function TracePanel({ entries }: { entries: TraceEntry[] }) {
  const [open, setOpen] = useState(false);
  return (
    <section aria-label="Agent 轨迹">
      <button
        onClick={() => {
          setOpen(!open);
        }}
      >
        轨迹
      </button>
      {open && (
        <ol>
          {entries.map((entry, index) => (
            <li key={index}>
              {entry.type === "llm" && (
                <div>
                  <strong>第 {formatValue(entry.turn)} 轮</strong>
                  <p>{formatValue(entry.response ?? "")}</p>
                  <small>
                    prompt_tokens={formatValue(entry.prompt_tokens ?? 0)} /
                    completion_tokens=
                    {formatValue(entry.completion_tokens ?? 0)} / latency_ms=
                    {formatValue(entry.latency_ms ?? 0)}
                  </small>
                </div>
              )}
              {entry.type === "tool" && (
                <div>
                  <strong>{formatValue(entry.tool)}</strong>
                  <span> {formatValue(entry.duration_ms)} ms</span>
                  <details>
                    <summary>参数与结果</summary>
                    <pre>{JSON.stringify(entry.args_redacted, null, 2)}</pre>
                    <p>{formatValue(entry.result_summary ?? "")}</p>
                  </details>
                </div>
              )}
              {entry.type === "stream" && (
                <span>{formatValue(entry.delta)}</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
