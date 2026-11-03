import { useState } from "react";
import { NodeResizer } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import ReactMarkdown from "react-markdown";
import type { FlowNode } from "../stores/workflowStore";
import { useWorkflowStore } from "../stores/workflowStore";

export function CanvasNote({ data, selected }: NodeProps<FlowNode>) {
  const [editing, setEditing] = useState(false);
  const markdown =
    typeof data.params.markdown === "string" ? data.params.markdown : "";
  const color =
    typeof data.params.color === "string" ? data.params.color : "#fef3c7";
  const update = (values: Record<string, unknown>) => {
    useWorkflowStore.getState().updateParams(data.nodeId, {
      ...data.params,
      ...values,
    });
  };
  return (
    <section
      aria-label="画布便签"
      className="canvas-note"
      style={{
        width: Number(data.params.width ?? 240),
        height: Number(data.params.height ?? 160),
        background: color,
      }}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={160}
        minHeight={100}
        onResizeEnd={(_, params) => {
          update({ width: params.width, height: params.height });
        }}
      />
      <div className="note-toolbar nodrag">
        <input
          aria-label="便签颜色"
          type="color"
          value={color}
          onChange={(event) => {
            update({ color: event.target.value });
          }}
          onPointerDown={(event) => {
            event.stopPropagation();
          }}
        />
        <button
          type="button"
          onClick={() => {
            setEditing(!editing);
          }}
        >
          {editing ? "预览便签" : "编辑便签"}
        </button>
      </div>
      {editing ? (
        <textarea
          aria-label="便签 Markdown"
          className="nodrag"
          value={markdown}
          onChange={(event) => {
            update({ markdown: event.target.value });
          }}
          onPointerDown={(event) => {
            event.stopPropagation();
          }}
        />
      ) : (
        <div className="note-markdown">
          <ReactMarkdown>{markdown}</ReactMarkdown>
        </div>
      )}
    </section>
  );
}
