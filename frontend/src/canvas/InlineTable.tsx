import { useEffect, useState } from "react";
import { tableFromIPC } from "apache-arrow";
import { sessionToken } from "../api/client";

function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (
    typeof value === "number" ||
    typeof value === "bigint" ||
    typeof value === "boolean"
  )
    return value.toString();
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return "";
}

export function InlineTable({
  workflowId,
  nodeId,
  rows = 10,
}: {
  workflowId: string;
  nodeId: string;
  rows?: number;
}) {
  const [table, setTable] = useState<string[][]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  useEffect(() => {
    const load = async () => {
      const response = await fetch(
        `/api/workflows/${workflowId}/nodes/${nodeId}/ports/out?offset=0&limit=${String(rows)}`,
        { headers: { Authorization: `Bearer ${sessionToken()}` } },
      );
      if (!response.ok) return;
      const data = tableFromIPC(await response.arrayBuffer());
      setColumns(data.schema.fields.map((field) => field.name));
      setTable(
        Array.from({ length: data.numRows }, (_, row) =>
          data.schema.fields.map((field) => {
            const value: unknown = data.getChild(field.name)?.get(row);
            return formatValue(value);
          }),
        ),
      );
    };
    void load();
  }, [workflowId, nodeId, rows]);
  return (
    <table className="inline-table">
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column}>{column}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {table.map((row, index) => (
          <tr key={index}>
            {row.map((value, cell) => (
              <td key={cell}>{value}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
