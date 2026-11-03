import { beforeEach, describe, expect, it } from "vitest";
import { toPortablePath } from "../panels/PathField";
import { toDocument, useWorkflowStore } from "./workflowStore";
import type { NodeTypeDecl, WorkflowDocument } from "../types/workflow";

const declaration: NodeTypeDecl = {
  type: "table.test",
  name: "Test",
  description: "Test",
  category: "table",
  cache_policy: "pure",
  inputs: [{ name: "in", kind: "table", description: "Input" }],
  outputs: [{ name: "out", kind: "table", description: "Output" }],
  params_schema: { properties: { path: { type: "string" } } },
};

const document: WorkflowDocument = {
  schema_version: 1,
  revision: 1,
  id: "wf_test",
  name: "test",
  description: "",
  created_at: "now",
  modified_at: "now",
  settings: {},
  variables: [],
  notes: [],
  nodes: [],
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },
};

describe("T2.2 editing contracts", () => {
  beforeEach(() => {
    useWorkflowStore.setState({
      nodes: [],
      edges: [],
      history: [],
      future: [],
      clipboard: null,
      selected: [],
      dirty: false,
      nodeTypes: [declaration],
      document,
    });
  });

  it("US-DES-04/AC-5: paths inside Root become relative and outside paths stay absolute", () => {
    expect(toPortablePath("C:/flows/demo/data/a.csv", "C:/flows/demo")).toBe(
      "data/a.csv",
    );
    expect(toPortablePath("D:/external/a.csv", "C:/flows/demo")).toBe(
      "D:/external/a.csv",
    );
  });

  it("US-DES-03/AC-1, US-DES-04/AC-2: serializes edges and resets downstream status", () => {
    const store = useWorkflowStore.getState();
    store.addNode(declaration.type, { x: 0, y: 0 });
    store.addNode(declaration.type, { x: 200, y: 0 });
    const [first, second] = useWorkflowStore.getState().nodes;
    useWorkflowStore.getState().connect({
      id: "e_00000001",
      source: first.id,
      sourceHandle: "out",
      target: second.id,
      targetHandle: "in",
    });
    const serialized = toDocument(
      useWorkflowStore.getState(),
      document.viewport,
    ) as {
      edges: {
        id: string;
        sourcePort: string;
        targetPort: string;
        order: number;
      }[];
    };
    expect(serialized.edges[0]).toEqual({
      id: "e_00000001",
      source: first.id,
      sourcePort: "out",
      target: second.id,
      targetPort: "in",
      order: 0,
    });
    useWorkflowStore.setState({
      nodes: useWorkflowStore.getState().nodes.map((node) => ({
        ...node,
        data: { ...node.data, status: "executed" },
      })),
    });
    useWorkflowStore.getState().updateParams(first.id, { path: "new.csv" });
    expect(
      useWorkflowStore.getState().nodes.map((node) => node.data.status),
    ).toEqual(["configured", "configured"]);
  });

  it("US-DES-08/AC-1: history retains at least fifty changes", () => {
    for (let index = 0; index < 60; index += 1)
      useWorkflowStore.getState().addNode(declaration.type, { x: index, y: 0 });
    expect(useWorkflowStore.getState().history.length).toBe(50);
  });

  it("US-DES-11/AC-3: viewport is persisted into workflow.json", () => {
    const result = toDocument(useWorkflowStore.getState(), {
      x: 10,
      y: 20,
      zoom: 1.5,
    });
    expect(result.viewport).toEqual({ x: 10, y: 20, zoom: 1.5 });
  });
});
