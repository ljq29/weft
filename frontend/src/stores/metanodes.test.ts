import { describe, expect, it } from "vitest";
import { collapseGraph, expandGraph, flowGraph } from "./metanodes";
import type { FlowEdge, FlowNode } from "./workflowStore";
import type { NodeTypeDecl } from "../types/workflow";

const declaration: NodeTypeDecl = {
  type: "table.test",
  name: "Test",
  description: "Test",
  category: "table",
  cache_policy: "pure",
  inputs: [{ name: "in", kind: "table", description: "Input" }],
  outputs: [{ name: "out", kind: "table", description: "Output" }],
  params_schema: {},
};

function node(id: string): FlowNode {
  return {
    id,
    type: "weft",
    position: { x: 0, y: 0 },
    data: {
      nodeId: id,
      type: declaration.type,
      name: id,
      params: {},
      inputs: declaration.inputs,
      outputs: declaration.outputs,
      comment: "",
      status: "configured",
    },
  };
}

function edge(id: string, source: string, target: string): FlowEdge {
  return { id, source, sourceHandle: "out", target, targetHandle: "in" };
}

describe("T7.1 Metanode editing", () => {
  it("US-DES-09/AC-1,3,4: collapse and expand preserve ports, nodes and edges", () => {
    const nodes = ["outside-in", "a", "b", "c", "outside-out"].map(node);
    const edges = [
      edge("e0", "outside-in", "a"),
      edge("e1", "a", "b"),
      edge("e2", "b", "c"),
      edge("e3", "c", "outside-out"),
    ];
    const folded = collapseGraph(
      nodes,
      edges,
      ["a", "b", "c"],
      [declaration],
      "n_00000001",
    );
    expect(folded.nodes).toHaveLength(3);
    const meta = folded.nodes.find((item) => item.id === "n_00000001");
    expect(meta?.data.inputs[0].kind).toBe("table");
    expect(meta?.data.outputs[0].kind).toBe("table");
    expect(folded.edges.find((item) => item.id === "e0")?.target).toBe(
      meta?.id,
    );
    expect(folded.edges.find((item) => item.id === "e3")?.source).toBe(
      meta?.id,
    );
    const child = flowGraph(meta?.data.params ?? {}, [declaration]);
    expect(child.nodes.map((item) => item.id)).toEqual(["a", "b", "c"]);
    expect(child.edges.map((item) => item.id)).toEqual(["e1", "e2"]);
    const expanded = expandGraph(folded.nodes, folded.edges, "n_00000001", [
      declaration,
    ]);
    expect(expanded.nodes.map((item) => item.id).sort()).toEqual(
      nodes.map((item) => item.id).sort(),
    );
    expect(expanded.edges.map((item) => item.id).sort()).toEqual(
      edges.map((item) => item.id).sort(),
    );
    expect(expanded.edges.find((item) => item.id === "e0")?.target).toBe("a");
    expect(expanded.edges.find((item) => item.id === "e3")?.source).toBe("c");
  });
});
