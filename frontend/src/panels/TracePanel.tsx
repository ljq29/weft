import { useState } from "react";
import { Icon } from "../components/Icon";

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
    <section className="inspector-section" aria-label="Agent 轨迹">
      <button
        className="section-toggle"
        onClick={() => {
          setOpen(!open);
        }}
      >
        <span>
          <Icon name="agent" />
          轨迹
        </span>
        <Icon name="down" className={open ? "rotated" : ""} />
      </button>
      {open && (
        <ol className="trace-list">
          {entries.map((entry, index) => (
            <li key={index}>
              <span className="trace-marker">
                <Icon name={entry.type === "tool" ? "trigger" : "agent"} />
              </span>
              <div>
                {entry.type === "llm" && (
                  <>
                    <strong>第 {formatValue(entry.turn)} 轮</strong>
                    <p>{formatValue(entry.response ?? "")}</p>
                    <small>
                      prompt={formatValue(entry.prompt_tokens ?? 0)} ·
                      completion={formatValue(entry.completion_tokens ?? 0)} ·{" "}
                      {formatValue(entry.latency_ms)} ms
                    </small>
                  </>
                )}
                {entry.type === "tool" && (
                  <>
                    <strong>{formatValue(entry.tool)}</strong>
                    <span> {formatValue(entry.duration_ms)} ms</span>
                    <details>
                      <summary>参数与结果</summary>
                      <pre>{JSON.stringify(entry.args_redacted, null, 2)}</pre>
                      <p>{formatValue(entry.result_summary ?? "")}</p>
                    </details>
                  </>
                )}
                {entry.type === "stream" && (
                  <span>{formatValue(entry.delta)}</span>
                )}
              </div>
            </li>
          ))}
          {entries.length === 0 && (
            <li className="section-empty">暂无 Agent 轨迹</li>
          )}
        </ol>
      )}
    </section>
  );
}
