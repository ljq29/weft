import { beforeEach, describe, expect, it } from "vitest";
import { useWorkflowStore } from "./workflowStore";
import type { NodeTypeDecl } from "../types/workflow";

const declaration: NodeTypeDecl = {
  type: "table.read_csv",
  name: "Read CSV",
  display_name: "读取 CSV",
  description: "Read CSV",
  category: "table",
  cache_policy: "pure",
  inputs: [],
  outputs: [{ name: "out", kind: "table", description: "Output" }],
  params_schema: {
    properties: { path: { type: "string", default: "data/a.csv" } },
  },
};

describe("T2.2 workflow editing store", () => {
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
    });
  });

  it("US-DES-02/AC-2,3: adds a node with defaults and stable id", () => {
    useWorkflowStore.getState().addNode(declaration.type, { x: 300, y: 200 });
    const node = useWorkflowStore.getState().nodes[0];
    expect(node.id).toMatch(/^n_[0-9a-f]{8}$/);
    expect(node.position).toEqual({ x: 300, y: 200 });
    expect(node.data.name).toBe("Read CSV");
    expect(node.data.name).not.toBe(declaration.display_name);
    expect(node.data.params).toEqual({ path: "data/a.csv" });
    expect(useWorkflowStore.getState().dirty).toBe(true);
  });

  it("US-DES-08/AC-1: undo and redo restore node edits", () => {
    useWorkflowStore.getState().addNode(declaration.type, { x: 0, y: 0 });
    const added = useWorkflowStore.getState().nodes[0];
    useWorkflowStore.getState().moveNodes([{ ...added, selected: true }]);
    expect(useWorkflowStore.getState().history).toHaveLength(1);
    useWorkflowStore.getState().undo();
    expect(useWorkflowStore.getState().nodes).toHaveLength(0);
    useWorkflowStore.getState().redo();
    expect(useWorkflowStore.getState().nodes).toHaveLength(1);
  });

  it("US-DES-08/AC-2,3: copy paste remaps ids and delete removes connected edges", () => {
    useWorkflowStore.getState().addNode(declaration.type, { x: 10, y: 20 });
    const id = useWorkflowStore.getState().nodes[0].id;
    useWorkflowStore.getState().setSelected([id]);
    useWorkflowStore.getState().copy();
    useWorkflowStore.getState().paste();
    const state = useWorkflowStore.getState();
    expect(state.nodes).toHaveLength(2);
    expect(state.nodes[1].id).not.toBe(id);
    expect(state.nodes[1].position).toEqual({ x: 50, y: 60 });
    useWorkflowStore.getState().setSelected([id, state.nodes[1].id]);
    useWorkflowStore.getState().deleteSelected();
    expect(useWorkflowStore.getState().nodes).toHaveLength(0);
  });

  it("US-DES-02/AC-3, US-DES-04/AC-3, US-DES-06/AC-2: marks missing required params and variable bindings", () => {
    const required = {
      ...declaration,
      params_schema: {
        properties: { path: { type: "string" } },
        required: ["path"],
      },
    };
    useWorkflowStore.setState({ nodeTypes: [required] });
    useWorkflowStore.getState().addNode(required.type, { x: 0, y: 0 });
    const id = useWorkflowStore.getState().nodes[0].id;
    expect(useWorkflowStore.getState().nodes[0].data.status).toBe(
      "unconfigured",
    );
    useWorkflowStore.getState().updateParams(id, { path: { $var: "input" } });
    const node = useWorkflowStore.getState().nodes[0];
    expect(node.data.status).toBe("configured");
    expect(node.data.params.path).toEqual({ $var: "input" });
  });

  it("US-DES-04/AC-3, US-DES-05/AC-1: applies and clears backend node validation errors", () => {
    useWorkflowStore.getState().addNode(declaration.type, { x: 0, y: 0 });
    const id = useWorkflowStore.getState().nodes[0].id;
    const historyLength = useWorkflowStore.getState().history.length;

    useWorkflowStore.getState().applyValidation([
      { code: "INVALID_PARAMS", message: "Invalid path", node_id: id },
      { code: "GRAPH_CYCLE", message: "Cycle", node_id: null },
    ]);
    expect(useWorkflowStore.getState().nodes[0].data.status).toBe(
      "unconfigured",
    );
    expect(useWorkflowStore.getState().history).toHaveLength(historyLength);

    useWorkflowStore.getState().applyValidation([]);
    expect(useWorkflowStore.getState().nodes[0].data.status).toBe("configured");
  });

  it("US-DES-05/AC-1,2: validation does not flatten runtime states", () => {
    const statuses = ["running", "executed", "failed", "skipped"];
    for (const status of statuses) {
      useWorkflowStore.getState().addNode(declaration.type, { x: 0, y: 0 });
      const nodes = useWorkflowStore.getState().nodes;
      const id = nodes.at(-1)?.id;
      useWorkflowStore.setState({
        nodes: nodes.map((node) =>
          node.id === id ? { ...node, data: { ...node.data, status } } : node,
        ),
      });
    }
    const before = useWorkflowStore.getState().nodes.map((node) => ({
      id: node.id,
      status: node.data.status,
    }));

    useWorkflowStore.getState().applyValidation(
      before.map(({ id }) => ({
        code: "INVALID_PARAMS",
        message: "Invalid",
        node_id: id,
      })),
    );

    expect(
      useWorkflowStore.getState().nodes.map((node) => node.data.status),
    ).toEqual(statuses);
  });
});
