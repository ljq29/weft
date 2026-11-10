import type { Connection } from "@xyflow/react";
import type { PortDecl, PortType } from "../types/workflow";
import type { FlowEdge, FlowNode } from "../stores/workflowStore";

function compatible(source: PortType, target: PortType): boolean {
  return (
    source === target ||
    (target === "flow" && source !== "tool" && source !== "flow")
  );
}

function reaches(edges: FlowEdge[], start: string, target: string): boolean {
  const pending = [start];
  const visited = new Set<string>();
  while (pending.length) {
    const current = pending.pop();
    if (current === undefined) break;
    if (current === target) return true;
    if (visited.has(current)) continue;
    visited.add(current);
    for (const edge of edges)
      if (edge.source === current) pending.push(edge.target);
  }
  return false;
}

function optionsFor(
  input: PortDecl,
  target: FlowNode,
  nodes: FlowNode[],
  edges: FlowEdge[],
) {
  return nodes.flatMap((source) => {
    if (source.id === target.id || reaches(edges, target.id, source.id))
      return [];
    return source.data.outputs
      .filter((output) => compatible(output.kind, input.kind))
      .map((output) => ({ source, output }));
  });
}

export function UpstreamOutputPicker({
  target,
  nodes,
  edges,
  onConnect,
}: {
  target: FlowNode;
  nodes: FlowNode[];
  edges: FlowEdge[];
  onConnect: (connection: Connection) => void | Promise<void>;
}) {
  return (
    <section className="upstream-picker" aria-label="上游输出选择">
      <h3>输入连接</h3>
      <p>从节点声明列出可连接输出；保存时仍由后端校验图与类型。</p>
      {target.data.inputs.map((input) => {
        const options = optionsFor(input, target, nodes, edges);
        const current = edges.find(
          (edge) =>
            edge.target === target.id && edge.targetHandle === input.name,
        );
        return (
          <label className="form-field" key={input.name}>
            <span>
              {input.name} · {input.kind}
            </span>
            <select
              aria-label={`输入 ${input.name}`}
              value={
                current ? `${current.source}:${current.sourceHandle ?? ""}` : ""
              }
              disabled={options.length === 0}
              onChange={(event) => {
                const [source, sourceHandle] = event.target.value.split(":");
                if (!source || !sourceHandle) return;
                void onConnect({
                  source,
                  sourceHandle,
                  target: target.id,
                  targetHandle: input.name,
                });
              }}
            >
              <option value="">选择上游输出…</option>
              {options.map(({ source, output }) => (
                <option
                  key={`${source.id}:${output.name}`}
                  value={`${source.id}:${output.name}`}
                >
                  {source.data.name} · {output.name} · {output.kind}
                </option>
              ))}
            </select>
          </label>
        );
      })}
    </section>
  );
}
