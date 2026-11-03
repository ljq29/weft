import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import type { FlowNode } from "../stores/workflowStore";
import { InlineTable } from "./InlineTable";

const colors = {
  table: "#3b82f6",
  excel: "#f97316",
  variable: "#ef4444",
  message: "#a855f7",
  tool: "#22c55e",
  flow: "#9ca3af",
};

export function WeftNode({ data }: NodeProps<FlowNode>) {
  return (
    <article
      className={`weft-node status-${data.status}`}
      title={data.error?.message}
    >
      <strong>{data.name}</strong>
      {data.error && (
        <span role="img" aria-label="错误">
          ×
        </span>
      )}
      <small>{data.type}</small>
      {data.inputs.map((port, index) => (
        <Handle
          key={port.name}
          id={port.name}
          type="target"
          position={Position.Left}
          title={`${port.name}: ${port.kind}`}
          style={{ top: 30 + index * 18, background: colors[port.kind] }}
        />
      ))}
      {data.outputs.map((port, index) => (
        <Handle
          key={port.name}
          id={port.name}
          type="source"
          position={Position.Right}
          title={`${port.name}: ${port.kind}`}
          style={{ top: 30 + index * 18, background: colors[port.kind] }}
        />
      ))}
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
          {port.name}
        </button>
      ))}
      {data.comment && <p title={data.comment}>{data.comment.slice(0, 60)}</p>}
      {data.iteration && (
        <span className="iteration-progress">
          {data.iteration.index} / {data.iteration.total}
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
      <span className="status-label">{data.status}</span>
    </article>
  );
}
