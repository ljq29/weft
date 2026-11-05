import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import type { FlowNode } from "../stores/workflowStore";
import { InlineTable } from "./InlineTable";
import { Icon, nodeVisual } from "../components/Icon";
import type { IconName } from "../components/Icon";

const colors = {
  table: "#417fc7",
  excel: "#25956f",
  variable: "#c07a26",
  message: "#8a62cc",
  tool: "#cc628e",
  flow: "#73717e",
};

const statusMeta: Record<string, { label: string; icon: IconName }> = {
  configured: { label: "已配置", icon: "info" },
  executed: { label: "已执行", icon: "check" },
  running: { label: "执行中", icon: "play" },
  failed: { label: "执行失败", icon: "warn" },
  unconfigured: { label: "未配置", icon: "warn" },
  skipped_branch: { label: "已跳过", icon: "stop" },
  skipped_upstream: { label: "已跳过", icon: "stop" },
  out_of_scope: { label: "范围外", icon: "stop" },
};

export function WeftNode({ data, selected }: NodeProps<FlowNode>) {
  const visual = nodeVisual(data.type);
  const status = statusMeta[data.status] ?? {
    label: data.status,
    icon: "info",
  };
  return (
    <article
      className={`weft-node status-${data.status}${selected ? " selected" : ""}`}
      title={data.error?.message}
    >
      <header className="node-header">
        <span className={`palette-icon ${visual.tone}`}>
          <Icon name={visual.icon} />
        </span>
        <div className="node-heading">
          <strong>{data.name}</strong>
          <small>{data.type}</small>
        </div>
        {data.error && (
          <span className="node-error" role="img" aria-label="错误">
            <Icon name="warn" />
          </span>
        )}
      </header>
      <div className="node-content">
        {data.comment && (
          <p title={data.comment}>{data.comment.slice(0, 60)}</p>
        )}
        {data.outputs.length > 0 && (
          <div className="node-outputs">
            {data.outputs.map((port) => (
              <button
                key={`preview-${port.name}`}
                className="nodrag port-preview"
                type="button"
                onPointerDown={(event) => {
                  event.stopPropagation();
                }}
                onClick={() => {
                  window.dispatchEvent(
                    new CustomEvent("weft-preview", {
                      detail: { nodeId: data.nodeId, port: port.name },
                    }),
                  );
                }}
              >
                <span>{port.name}</span>
                <Icon name="eye" />
              </button>
            ))}
          </div>
        )}
        {data.iteration && (
          <span className="iteration-progress">
            迭代 {data.iteration.index} / {data.iteration.total}
          </span>
        )}
        {data.type === "table.view" &&
          data.status === "executed" &&
          data.workflowId && (
            <InlineTable
              workflowId={data.workflowId}
              nodeId={data.nodeId}
              rows={Number(data.params.rows ?? 10)}
            />
          )}
      </div>
      <footer className="node-status">
        <Icon name={status.icon} />
        <span className="status-label">{status.label}</span>
      </footer>
      {data.inputs.map((port, index) => (
        <Handle
          key={port.name}
          id={port.name}
          type="target"
          position={Position.Left}
          title={`${port.name}: ${port.kind}`}
          style={{ top: 46 + index * 18, background: colors[port.kind] }}
        />
      ))}
      {data.outputs.map((port, index) => (
        <Handle
          key={port.name}
          id={port.name}
          type="source"
          position={Position.Right}
          title={`${port.name}: ${port.kind}`}
          style={{ top: 46 + index * 18, background: colors[port.kind] }}
        />
      ))}
    </article>
  );
}
