import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { useWorkflowStore } from "../stores/workflowStore";
import type { WorkflowDocument } from "../types/workflow";
import { useWorkflowDocument } from "./useWorkflowDocument";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: vi.fn() };
});

const apiMock = vi.mocked(api);

function serverDocument(comment: string, revision: number): WorkflowDocument {
  return {
    schema_version: 1,
    revision,
    id: "wf_1",
    name: "conflict",
    description: "",
    created_at: "2025-01-01T00:00:00Z",
    modified_at: "2025-01-01T00:00:00Z",
    settings: {},
    variables: [],
    notes: [],
    viewport: { x: 0, y: 0, zoom: 1 },
    nodes: [
      {
        id: "n_1",
        type: "flow.variable",
        node_version: 1,
        name: "Variable",
        position: { x: 0, y: 0 },
        params: {},
        comment,
      },
    ],
    edges: [],
  };
}

function documentControls(setError: (error: string) => void) {
  let controls!: ReturnType<typeof useWorkflowDocument>;
  function Harness() {
    controls = useWorkflowDocument({ setError });
    return null;
  }
  renderToStaticMarkup(<Harness />);
  return controls;
}

describe("workflow document revision recovery", () => {
  beforeEach(() => {
    apiMock.mockReset();
    useWorkflowStore.setState({
      document: null,
      nodes: [],
      edges: [],
      selected: [],
      dirty: false,
      history: [],
      future: [],
      clipboard: null,
      nodeTypes: [],
    });
  });

  it("US-DES-07/AC-4: keeps local edits until an explicit reload replaces them", async () => {
    const setError = vi.fn();
    const controls = documentControls(setError);
    controls.load(serverDocument("初始版本", 1));
    useWorkflowStore.getState().updateComment("n_1", "本地未保存");
    useWorkflowStore.getState().setSelected(["n_1"]);
    apiMock.mockRejectedValue(
      new ApiError(409, "REVISION_CONFLICT", "工作流已被修改"),
    );

    await controls.save();

    expect(useWorkflowStore.getState().dirty).toBe(true);
    expect(useWorkflowStore.getState().nodes[0].data.comment).toBe(
      "本地未保存",
    );
    expect(setError).toHaveBeenLastCalledWith(
      "工作流已被修改（REVISION_CONFLICT）",
    );
    expect(apiMock).toHaveBeenCalledTimes(1);
    expect(apiMock).toHaveBeenLastCalledWith(
      "/workflows/wf_1",
      expect.objectContaining({ method: "PUT" }),
    );

    apiMock.mockImplementation(() =>
      Promise.resolve(serverDocument("服务端版本", 2)),
    );
    await controls.reload();

    expect(apiMock).toHaveBeenCalledTimes(2);
    expect(apiMock).toHaveBeenLastCalledWith("/workflows/wf_1");
    expect(useWorkflowStore.getState().dirty).toBe(false);
    expect(useWorkflowStore.getState().nodes[0].data.comment).toBe(
      "服务端版本",
    );
    expect(useWorkflowStore.getState().selected).toEqual(["n_1"]);
    expect(useWorkflowStore.getState().nodes[0].selected).toBe(true);
    expect(useWorkflowStore.getState().document?.revision).toBe(2);
    expect(setError).toHaveBeenLastCalledWith("");
  });
});
