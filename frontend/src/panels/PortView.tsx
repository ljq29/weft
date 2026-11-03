import { useEffect, useState } from "react";
import { tableFromIPC } from "apache-arrow";
import { sessionToken } from "../api/client";

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
        setError(String(reason));
      }
    };
    void load();
  }, [workflowId, runId, nodeId, port, offset, sortBy, descending]);
  return (
    <div className="modal-backdrop" role="dialog" aria-label="端口预览">
      <section className="port-view">
        <button onClick={onClose}>关闭</button>
        <button
          disabled={offset === 0}
          onClick={() => {
            setOffset(Math.max(0, offset - 100));
          }}
        >
          上一页
        </button>
        <button
          disabled={offset + 100 >= total}
          onClick={() => {
            setOffset(offset + 100);
          }}
        >
          下一页
        </button>
        <span>共 {total} 行，每页 100 行</span>
        {error && <p role="alert">{error}</p>}
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>
                  <button
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
                      onClick={() => {
                        void navigator.clipboard.writeText(formatValue(value));
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
      </section>
    </div>
  );
}
