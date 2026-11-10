import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { FlowNode } from "../stores/workflowStore";
import type { PortType } from "../types/workflow";
import { UpstreamOutputPicker } from "./UpstreamOutputPicker";

function node(id: string, kind: PortType): FlowNode {
  return {
    id,
    type: "weft",
    position: { x: 0, y: 0 },
    data: {
      nodeId: id,
      type: `test.${id}`,
      name: id,
      params: {},
      inputs: [{ name: "in", kind, description: "" }],
      outputs: [{ name: "out", kind, description: "" }],
      comment: "",
      status: "configured",
    },
  };
}

describe("Windmill-inspired upstream output selection", () => {
  it("US-DES-03/AC-7: lists compatible outputs without offering cyclic connections", () => {
    const target = node("target", "table");
    const read = node("read", "table");
    const variable = node("variable", "variable");
    const cyclic = node("cyclic", "table");
    const html = renderToStaticMarkup(
      <UpstreamOutputPicker
        target={target}
        nodes={[target, read, variable, cyclic]}
        edges={[
          {
            id: "e_1",
            source: "target",
            sourceHandle: "out",
            target: "cyclic",
            targetHandle: "in",
          },
        ]}
        onConnect={() => {}}
      />,
    );

    expect(html).toContain("read · out · table");
    expect(html).not.toContain("variable · out · variable");
    expect(html).not.toContain("cyclic · out · table");
    expect(html).toContain("后端校验");
  });
});
