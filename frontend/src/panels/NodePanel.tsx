import { useMemo, useState } from "react";
import type { NodeTypeDecl } from "../types/workflow";
import { Icon, nodeVisual } from "../components/Icon";

const categoryDisplayNames: Record<string, string> = {
  agent: "智能体",
  code: "代码",
  excel: "Excel",
  file: "文件",
  flow: "流程控制",
  table: "表格",
  user: "自定义",
};

export function filterNodeTypes(
  types: NodeTypeDecl[],
  query: string,
): NodeTypeDecl[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return types;
  return types.filter((item) =>
    [item.name, item.display_name, item.type, item.description].some((value) =>
      value.toLocaleLowerCase().includes(normalized),
    ),
  );
}

export function NodePanel({
  types,
  onAdd,
}: {
  types: NodeTypeDecl[];
  onAdd: (type: string) => void;
}) {
  const [query, setQuery] = useState("");
  const groups = useMemo(() => {
    const filtered = filterNodeTypes(types, query);
    const result = new Map<string, NodeTypeDecl[]>();
    for (const item of filtered) {
      result.set(item.category, [...(result.get(item.category) ?? []), item]);
    }
    return result;
  }, [types, query]);
  return (
    <aside className="node-panel" aria-label="节点面板">
      <div className="panel-title">
        <div>
          <h2>节点</h2>
          <span>{types.length} 个可用</span>
        </div>
        <Icon name="grid" />
      </div>
      <div className="search-field node-search">
        <Icon name="search" />
        <input
          aria-label="搜索节点"
          placeholder="搜索节点…"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
      </div>
      <div className="node-categories">
        {[...groups.entries()].map(([category, nodes]) => (
          <section className="node-category" key={category}>
            <h3>
              <span>{categoryDisplayNames[category] ?? category}</span>
              <span>{nodes.length}</span>
            </h3>
            <div className="category-nodes">
              {nodes.map((node) => {
                const visual = nodeVisual(node.type, node.category);
                return (
                  <button
                    className="palette-node"
                    key={node.type}
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData(
                        "application/weft-node",
                        node.type,
                      );
                    }}
                    onDoubleClick={() => {
                      onAdd(node.type);
                    }}
                    title={node.description}
                  >
                    <span className={`palette-icon ${visual.tone}`}>
                      <Icon name={visual.icon} />
                    </span>
                    <span className="palette-node-name">
                      {node.name}
                      {node.display_name && (
                        <span className="palette-node-display-name">
                          {" · "}
                          {node.display_name}
                        </span>
                      )}
                    </span>
                    <Icon name="plus" className="add-icon" />
                  </button>
                );
              })}
            </div>
          </section>
        ))}
        {groups.size === 0 && (
          <div className="palette-empty">
            <Icon name="search" />
            <p>没有匹配的节点</p>
            <span>试试其他关键词</span>
          </div>
        )}
      </div>
      <footer className="node-panel-footer">
        <Icon name="info" />
        <span>拖拽或双击节点添加到画布</span>
      </footer>
    </aside>
  );
}
