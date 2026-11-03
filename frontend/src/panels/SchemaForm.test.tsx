import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SchemaForm } from "./SchemaForm";
import type { NodeTypeDecl, WorkflowNodeData } from "../types/workflow";

const declaration: NodeTypeDecl = {
  type: "table.row_filter",
  name: "Row Filter",
  description: "Filter rows",
  category: "table",
  cache_policy: "pure",
  inputs: [],
  outputs: [],
  params_schema: {
    properties: {
      column: { type: "string", description: "Column" },
      operator: { type: "string", enum: ["=="] },
      value: { type: "string" },
    },
    required: ["column", "operator"],
  },
};

const node: WorkflowNodeData = {
  nodeId: "n_00000001",
  type: declaration.type,
  name: declaration.name,
  params: { column: "amount", operator: "==", value: "100" },
  inputs: [],
  outputs: [],
  comment: "",
  status: "configured",
};

describe("T2.2 schema form", () => {
  it("US-DES-04/AC-1,3: generates row filter fields and required indicators", () => {
    const html = renderToStaticMarkup(
      <SchemaForm
        node={node}
        declaration={declaration}
        onChange={() => undefined}
        root="C:/flow"
        columnHints={["amount", "region"]}
        variables={["target_wb"]}
      />,
    );
    expect(html).toContain("column");
    expect(html).toContain("operator");
    expect(html).toContain("value");
    expect(html).toContain("amount");
    expect(html).toContain("region");
  });

  it("US-DES-06/AC-1: variable binding lists available variables", () => {
    const bound = { ...node, params: { value: { $var: "target_wb" } } };
    const html = renderToStaticMarkup(
      <SchemaForm
        node={bound}
        declaration={declaration}
        onChange={() => undefined}
        root="C:/flow"
        columnHints={[]}
        variables={["target_wb"]}
      />,
    );
    expect(html).toContain("target_wb");
    expect(html).toContain("datalist");
  });
});
