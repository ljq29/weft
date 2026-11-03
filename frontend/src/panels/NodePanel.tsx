import { useMemo, useState } from "react";
import type { NodeTypeDecl } from "../types/workflow";

export function NodePanel({
  types,
  onAdd,
}: {
  types: NodeTypeDecl[];
  onAdd: (type: string) => void;
}) {
  const [query, setQuery] = useState("");
  const groups = useMemo(() => {
    const filtered = types.filter((item) =>
      `${item.name} ${item.description}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    );
    const result = new Map<string, NodeTypeDecl[]>();
    for (const item of filtered) {
      result.set(item.category, [...(result.get(item.category) ?? []), item]);
    }
    return result;
  }, [types, query]);
  return (
    <aside className="node-panel" aria-label="节点面板">
      <input
        aria-label="搜索节点"
        placeholder="搜索节点"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
        }}
      />
      {[...groups.entries()].map(([category, nodes]) => (
        <section key={category}>
          <h3>{category}</h3>
          {nodes.map((node) => (
            <button
              key={node.type}
              draggable
              onDragStart={(event) => {
                event.dataTransfer.setData("application/weft-node", node.type);
              }}
              onDoubleClick={() => {
                onAdd(node.type);
              }}
              title={node.description}
            >
              {node.name}
            </button>
          ))}
        </section>
      ))}
    </aside>
  );
}
