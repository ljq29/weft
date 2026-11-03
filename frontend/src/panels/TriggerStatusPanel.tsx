import { useEffect, useState } from "react";
import { api } from "../api/client";

interface Props {
  workflowId: string;
  params: Record<string, unknown>;
}
interface ScheduleInfo {
  schedule_id: string;
  next_at: string | null;
}
interface SourceHealth {
  status?: string;
  next?: ScheduleInfo[];
}
type Health = Record<string, SourceHealth | undefined>;
const sources = [
  ["manual", "手动"],
  ["chat", "聊天"],
  ["schedule", "定时"],
  ["watch", "文件"],
  ["http", "HTTP"],
] as const;

export function TriggerStatusPanel({ workflowId, params }: Props) {
  const [health, setHealth] = useState<Health>({});
  useEffect(() => {
    void api<Health>(`/workflows/${workflowId}/triggers/status`)
      .then((health) => {
        setHealth(health);
      })
      .catch(() => {
        setHealth({});
      });
  }, [workflowId, params]);
  return (
    <section aria-label="触发来源状态">
      {sources.map(([key, label]) => {
        const config = params[key] as { enabled?: boolean } | undefined;
        const error = health[key]?.status === "error";
        return (
          <span
            key={key}
            style={{
              color: error ? "#d00" : config?.enabled ? "#080" : "#888",
            }}
          >
            {label}: {error ? "异常" : config?.enabled ? "启用" : "禁用"}
          </span>
        );
      })}
      {(health.schedule?.next ?? []).map((item) => (
        <div key={item.schedule_id}>下次触发：{item.next_at ?? "未安排"}</div>
      ))}
    </section>
  );
}
