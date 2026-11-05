import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { filterNodeTypes, NodePanel } from "./NodePanel";
import type { NodeTypeDecl } from "../types/workflow";

const declarations: NodeTypeDecl[] = [
  {
    type: "table.read_csv",
    name: "Read CSV",
    display_name: "读取 CSV",
    description: "Read comma-separated files",
    category: "table",
    cache_policy: "pure",
    inputs: [],
    outputs: [],
    params_schema: {},
  },
  {
    type: "agent.llm_call",
    name: "LLM Call",
    display_name: "大模型调用",
    description: "Generate structured output",
    category: "agent",
    cache_policy: "volatile",
    inputs: [],
    outputs: [],
    params_schema: {},
  },
];

function matchingTypes(query: string): string[] {
  return filterNodeTypes(declarations, query).map((item) => item.type);
}

describe("NodePanel bilingual declarations", () => {
  it("US-DES-02/AC-1: searches Chinese, English, type and description", () => {
    expect(matchingTypes("大模型")).toEqual(["agent.llm_call"]);
    expect(matchingTypes("read csv")).toEqual(["table.read_csv"]);
    expect(matchingTypes("agent.llm")).toEqual(["agent.llm_call"]);
    expect(matchingTypes("STRUCTURED")).toEqual(["agent.llm_call"]);
    expect(matchingTypes("missing")).toEqual([]);
  });

  it("US-DES-02/AC-1: renders English names first with Chinese supplements", () => {
    const html = renderToStaticMarkup(
      <NodePanel types={declarations} onAdd={() => undefined} />,
    );
    expect(html).toContain("LLM Call");
    expect(html).toContain("大模型调用");
    expect(html.indexOf("LLM Call")).toBeLessThan(html.indexOf("大模型调用"));
    expect(html).toContain("智能体");
    expect(declarations[1].category).toBe("agent");
  });
});
