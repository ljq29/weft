import { useEffect, useState } from "react";
import { tableFromIPC } from "apache-arrow";
import { formatApiError, sessionToken } from "../api/client";
import { Icon } from "../components/Icon";

interface Row {
  values: unknown[];
}

function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return value.toString();
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return "";
}

export function PortView({
  workflowId,
  runId,
  nodeId,
  port,
  onClose,
}: {
  workflowId: string;
  runId: string;
  nodeId: string;
  port: string;
  onClose: () => void;
}) {
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [sortBy, setSortBy] = useState("");
  const [descending, setDescending] = useState(false);
  const [error, setError] = useState("");
  const [jsonValue, setJsonValue] = useState<{ value: unknown } | null>(null);
  useEffect(() => {
    const load = async () => {
      try {
        const query = new URLSearchParams({
          offset: String(offset),
          limit: "100",
          sort_by: sortBy,
          desc: String(descending),
        });
        const base = runId
          ? `/api/runs/${runId}/nodes/${nodeId}/ports/${port}`
          : `/api/workflows/${workflowId}/nodes/${nodeId}/ports/${port}`;
        const response = await fetch(`${base}?${query}`, {
          headers: { Authorization: `Bearer ${sessionToken()}` },
        });
        if (!response.ok) throw new Error("节点未执行");
        setError("");
        if (
          response.headers.get("content-type")?.includes("application/json")
        ) {
          setJsonValue({ value: (await response.json()) as unknown });
          setColumns([]);
          setRows([]);
          setTotal(1);
          return;
        }
        setJsonValue(null);
        const table = tableFromIPC(await response.arrayBuffer());
        setColumns(table.schema.fields.map((field) => field.name));
        setTotal(
          Number(response.headers.get("X-Weft-Total-Rows") ?? table.numRows),
        );
        setRows(
          Array.from({ length: table.numRows }, (_, index) => ({
            values: table.schema.fields.map((field) => {
              const value: unknown = table.getChild(field.name)?.get(index);
              return value;
            }),
          })),
        );
      } catch (reason) {
        setError(formatApiError(reason));
      }
    };
    void load();
  }, [workflowId, runId, nodeId, port, offset, sortBy, descending]);
  return (
    <div className="modal-backdrop" role="dialog" aria-label="端口预览">
      <section className="modal port-view">
        <header className="modal-header">
          <div>
            <span className="dialog-icon">
              <Icon name="table" />
            </span>
            <div>
              <h2>端口预览</h2>
              <p>
                {nodeId} · {port} · 只读数据快照
              </p>
            </div>
          </div>
          <button className="icon-button" aria-label="关闭" onClick={onClose}>
            <Icon name="close" />
          </button>
        </header>
        <div className="table-meta">
          <span>
            <strong>{total}</strong> 行
          </span>
          <span>每页 100 行</span>
          {sortBy && (
            <span className="tag neutral">
              按 {sortBy} {descending ? "降序" : "升序"}
            </span>
          )}
        </div>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        {jsonValue && (
          <pre className="json-preview">
            {JSON.stringify(jsonValue.value, null, 2)}
          </pre>
        )}
        {!jsonValue && (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={column}>
                      <button
                        className="sort-button"
                        onClick={() => {
                          if (sortBy === column) setDescending(!descending);
                          else {
                            setSortBy(column);
                            setDescending(false);
                          }
                          setOffset(0);
                        }}
                      >
                        {column}
                        {sortBy === column && (
                          <Icon
                            name="down"
                            className={descending ? "rotated" : ""}
                          />
                        )}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index}>
                    {row.values.map((value, cell) => (
                      <td key={cell}>
                        <button
                          className="cell-value"
                          title="点击复制"
                          onClick={() => {
                            void navigator.clipboard.writeText(
                              formatValue(value),
                            );
                          }}
                        >
                          {formatValue(value)}
                        </button>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && !error && (
              <div className="bottom-empty">暂无可预览数据</div>
            )}
          </div>
        )}
        <footer className="modal-footer">
          <span>
            显示 {total === 0 ? 0 : offset + 1}–{Math.min(offset + 100, total)}
            ，共 {total} 行
          </span>
          <div>
            <button
              className="button secondary"
              disabled={offset === 0}
              onClick={() => {
                setOffset(Math.max(0, offset - 100));
              }}
            >
              上一页
            </button>
            <button
              className="button secondary"
              disabled={offset + 100 >= total}
              onClick={() => {
                setOffset(offset + 100);
              }}
            >
              下一页
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
