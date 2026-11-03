import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  useReactFlow,
} from "@xyflow/react";
import type { Connection, Edge, NodeChange } from "@xyflow/react";
import { api } from "./api/client";
import { AuditPanel } from "./panels/AuditPanel";
import { WeftNode } from "./canvas/WeftNode";
import { CanvasNote } from "./canvas/CanvasNote";
import { connectRuns } from "./api/ws";
import { LogPanel } from "./panels/LogPanel";
import { PortView } from "./panels/PortView";
import { NodePanel } from "./panels/NodePanel";
import { SchemaForm } from "./panels/SchemaForm";
import { SettingsPanel } from "./panels/SettingsPanel";
import { TracePanel } from "./panels/TracePanel";
import { ChatPanel } from "./panels/ChatPanel";
import { ChangeReviewPanel } from "./panels/ChangeReviewPanel";
import { ConfirmPanel } from "./panels/ConfirmPanel";
import { TriggerStatusPanel } from "./panels/TriggerStatusPanel";
import { HistoryPanel } from "./panels/HistoryPanel";
import { useRunStore } from "./stores/runStore";
import {
  collapseGraph,
  expandGraph,
  flowGraph,
  metanodePorts,
} from "./stores/metanodes";
import { toDocument, useWorkflowStore } from "./stores/workflowStore";
import type { FlowNode } from "./stores/workflowStore";
import type { NodeTypeDecl, WorkflowDocument } from "./types/workflow";
import "@xyflow/react/dist/style.css";
import "./styles.css";

let saveQueue: Promise<void> = Promise.resolve();

interface StoredNode {
  id: string;
  type: string;
  name: string;
  position: { x: number; y: number };
  params: Record<string, unknown>;
  comment?: string;
}

interface StoredEdge {
  id: string;
  source: string;
  sourcePort: string;
  target: string;
  targetPort: string;
}

function Editor() {
  const store = useWorkflowStore();
  const run = useRunStore();
  const [preview, setPreview] = useState<{
    nodeId: string;
    port: string;
    runId?: string;
  } | null>(null);
  const [menu, setMenu] = useState<{
    nodeId: string;
    x: number;
    y: number;
  } | null>(null);
  const setNodeTypes = useWorkflowStore((state) => state.setNodeTypes);
  const [error, setError] = useState("");
  const [serverWarning, setServerWarning] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [name, setName] = useState("weekly");
  const [parent, setParent] = useState("C:/flows");
  const [root, setRoot] = useState("");
  const [columnHints, setColumnHints] = useState<string[]>([]);
  const [pathIssues, setPathIssues] = useState<
    { node_id: string; param: string; value: string }[]
  >([]);
  const flow = useReactFlow();
  const viewport = useRef({ x: 0, y: 0, zoom: 1 });
  const graphStack = useRef<
    { nodes: FlowNode[]; edges: typeof store.edges; id: string; name: string }[]
  >([]);
  const [breadcrumbs, setBreadcrumbs] = useState<
    { id: string; name: string }[]
  >([]);
  const nodeTypes = useMemo(
    () => new Map(store.nodeTypes.map((item) => [item.type, item])),
    [store.nodeTypes],
  );

  const save = useCallback(() => {
    const operation = saveQueue.then(async () => {
      const state = useWorkflowStore.getState();
      if (!state.document || graphStack.current.length) return;
      try {
        const document = toDocument(state, viewport.current);
        const saved = await api<WorkflowDocument>(
          `/workflows/${state.document.id}`,
          { method: "PUT", body: JSON.stringify(document) },
        );
        state.markSaved(saved.revision);
        setError("");
      } catch (reason) {
        setError(String(reason));
      }
    });
    saveQueue = operation;
    return operation;
  }, []);

  useEffect(() => {
    void api<NodeTypeDecl[]>("/nodes/types")
      .then((types) => {
        setNodeTypes(types);
      })
      .catch((reason: unknown) => {
        setError(String(reason));
      });
  }, [setNodeTypes]);

  useEffect(() => {
    void api<{ warning: string }>("/system/version")
      .then((system) => {
        setServerWarning(system.warning);
      })
      .catch(() => {
        setServerWarning("");
      });
  }, []);

  useEffect(() => {
    if (!store.document) return;
    return connectRuns(store.document.id);
  }, [store.document]);

  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<{ nodeId: string; port: string }>)
        .detail;
      setPreview(detail);
    };
    window.addEventListener("weft-preview", listener);
    return () => {
      window.removeEventListener("weft-preview", listener);
    };
  }, []);

  useEffect(() => {
    if (!store.dirty) return;
    const timer = window.setTimeout(() => {
      void save();
    }, 2000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [store.dirty, store.nodes, store.edges, save]);

  useEffect(() => {
    const actions = useWorkflowStore.getState();
    const listener = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      if (event.shiftKey && key === "1") {
        event.preventDefault();
        void flow.fitView();
        return;
      }
      if (event.shiftKey && key === "2") {
        event.preventDefault();
        const selected = useWorkflowStore
          .getState()
          .nodes.filter((node) => node.selected);
        if (selected.length) void flow.fitView({ nodes: selected });
        return;
      }
      if (!event.ctrlKey) return;
      if (key === "s") {
        event.preventDefault();
        void save();
      }
      if (key === "z") {
        event.preventDefault();
        actions.undo();
      }
      if (key === "y") {
        event.preventDefault();
        actions.redo();
      }
      if (key === "c") {
        actions.copy();
      }
      if (key === "v") {
        actions.paste();
      }
    };
    const deleteListener = (event: KeyboardEvent) => {
      if (event.key === "Delete") actions.deleteSelected();
    };
    window.addEventListener("keydown", listener);
    window.addEventListener("keyup", deleteListener);
    return () => {
      window.removeEventListener("keydown", listener);
      window.removeEventListener("keyup", deleteListener);
    };
  }, [save, flow]);

  const load = (
    document: WorkflowDocument & { nodes: unknown[]; edges: unknown[] },
  ) => {
    graphStack.current = [];
    setBreadcrumbs([]);
    const nodes = document.nodes.map((raw) => {
      const node = raw as StoredNode;
      const ports =
        node.type === "flow.metanode"
          ? metanodePorts(node.params, store.nodeTypes)
          : {
              inputs: nodeTypes.get(node.type)?.inputs ?? [],
              outputs: nodeTypes.get(node.type)?.outputs ?? [],
            };
      return {
        id: node.id,
        type: "weft",
        position: node.position,
        data: {
          nodeId: node.id,
          type: node.type,
          name: node.name,
          params: node.params,
          inputs: ports.inputs,
          outputs: ports.outputs,
          comment: node.comment ?? "",
          status: "configured",
        },
      };
    });
    const notes: FlowNode[] = document.notes.map((note) => ({
      id: note.id,
      type: "note",
      position: note.position,
      data: {
        nodeId: note.id,
        type: "canvas.note",
        name: "便签",
        params: {
          markdown: note.markdown,
          color: note.color,
          width: note.size.width,
          height: note.size.height,
        },
        inputs: [],
        outputs: [],
        comment: "",
        status: "configured",
      },
    }));
    const edges = document.edges.map((raw) => {
      const edge = raw as StoredEdge;
      return {
        id: edge.id,
        source: edge.source,
        sourceHandle: edge.sourcePort,
        target: edge.target,
        targetHandle: edge.targetPort,
      };
    });
    store.setDocument(document, [...nodes, ...notes], edges);
    viewport.current = document.viewport;
  };

  const create = async () => {
    const result = await api<{ id: string; path: string }>("/workflows", {
      method: "POST",
      body: JSON.stringify({ name, parent_dir: parent }),
    });
    setRoot(result.path);
    const document = await api<
      WorkflowDocument & { nodes: unknown[]; edges: unknown[] }
    >(`/workflows/${result.id}`);
    load(document);
  };

  const open = async () => {
    const path = window.prompt("工作流目录");
    if (!path) return;
    const result = await api<{ id: string; path: string }>("/workflows/open", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    setRoot(result.path);
    const document = await api<
      WorkflowDocument & { nodes: unknown[]; edges: unknown[] }
    >(`/workflows/${result.id}`);
    load(document);
  };

  const importWorkflow = async () => {
    const zipPath = window.prompt("工作流 zip 路径");
    if (!zipPath) return;
    const destDir = window.prompt("导入目标父目录", parent);
    if (!destDir) return;
    try {
      const result = await api<{ id: string; path: string }>(
        "/workflows/unpack",
        {
          method: "POST",
          body: JSON.stringify({ zip_path: zipPath, dest_dir: destDir }),
        },
      );
      setRoot(result.path);
      const document = await api<
        WorkflowDocument & { nodes: unknown[]; edges: unknown[] }
      >(`/workflows/${result.id}`);
      load(document);
      setError("");
    } catch (reason) {
      setError(String(reason));
    }
  };

  const pack = async () => {
    const document = store.document;
    if (!document) return;
    try {
      const report = await api<{
        errors: { message: string }[];
        warnings: { message: string }[];
        abs_paths: { node_id: string; param: string; value: string }[];
        size_estimate: number;
      }>(`/workflows/${document.id}/pack/preflight`);
      setPathIssues(report.abs_paths);
      if (report.errors.length) {
        setError(report.errors.map((item) => item.message).join("\n"));
        return;
      }
      const summary = report.warnings.map((item) => item.message).join("\n");
      if (
        report.warnings.length &&
        !window.confirm(`发现打包警告：\n${summary}\n是否继续？`)
      )
        return;
      const result = await api<{ path: string }>(
        `/workflows/${document.id}/pack`,
        {
          method: "POST",
          body: JSON.stringify({
            exclude_data: window.confirm("是否排除 data/ 数据目录？"),
            confirm_warnings: true,
          }),
        },
      );
      window.alert(`打包完成：${result.path}`);
      setError("");
    } catch (reason) {
      setError(String(reason));
    }
  };

  const collapse = () => {
    const state = useWorkflowStore.getState();
    const selected = state.selected.filter(
      (id) =>
        state.nodes.find((node) => node.id === id)?.data.type !== "canvas.note",
    );
    if (!selected.length) return;
    const metaId = `n_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
    const graph = collapseGraph(
      store.nodes,
      store.edges,
      selected,
      store.nodeTypes,
      metaId,
    );
    store.setGraph(graph.nodes, graph.edges);
    store.setSelected([metaId]);
  };

  const expand = (nodeId: string) => {
    const graph = expandGraph(
      store.nodes,
      store.edges,
      nodeId,
      store.nodeTypes,
    );
    store.setGraph(graph.nodes, graph.edges);
    setMenu(null);
  };

  const enterMetanode = (node: FlowNode) => {
    if (node.data.type !== "flow.metanode") return;
    const graph = flowGraph(node.data.params, store.nodeTypes);
    graphStack.current.push({
      nodes: store.nodes,
      edges: store.edges,
      id: node.id,
      name: node.data.name,
    });
    setBreadcrumbs([
      ...graphStack.current.map((item) => ({ id: item.id, name: item.name })),
    ]);
    useWorkflowStore.setState({
      nodes: graph.nodes,
      edges: graph.edges,
      selected: [],
      history: [],
      future: [],
      dirty: false,
    });
  };

  const leaveMetanode = () => {
    const parent = graphStack.current.pop();
    if (!parent) return;
    const meta = parent.nodes.find((node) => node.id === parent.id);
    if (!meta) throw new Error("Metanode 不存在");
    const params = {
      ...meta.data.params,
      graph: {
        nodes: store.nodes
          .filter((node) => node.data.type !== "canvas.note")
          .map((node) => ({
            id: node.id,
            type: node.data.type,
            name: node.data.name,
            position: node.position,
            params: node.data.params,
            comment: node.data.comment,
          })),
        notes: store.nodes
          .filter((node) => node.data.type === "canvas.note")
          .map((node) => ({
            id: node.id,
            position: node.position,
            size: {
              width: Number(node.data.params.width ?? 240),
              height: Number(node.data.params.height ?? 160),
            },
            color:
              typeof node.data.params.color === "string"
                ? node.data.params.color
                : "#fef3c7",
            markdown:
              typeof node.data.params.markdown === "string"
                ? node.data.params.markdown
                : "",
          })),
        edges: store.edges.map((edge, order) => ({
          id: edge.id,
          source: edge.source,
          sourcePort: edge.sourceHandle,
          target: edge.target,
          targetPort: edge.targetHandle,
          order,
        })),
      },
    };
    useWorkflowStore.setState({
      nodes: parent.nodes.map((node) =>
        node.id === parent.id
          ? { ...node, data: { ...node.data, params } }
          : node,
      ),
      edges: parent.edges,
      selected: [parent.id],
      history: [],
      future: [],
      dirty: true,
    });
    setBreadcrumbs(
      graphStack.current.map((item) => ({ id: item.id, name: item.name })),
    );
  };

  const addAtCenter = (type: string) => {
    store.addNode(
      type,
      flow.screenToFlowPosition({
        x: window.innerWidth / 2,
        y: window.innerHeight / 2,
      }),
    );
  };

  const connect = async (connection: Connection) => {
    const edge: Edge = {
      ...connection,
      id: `e_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`,
    };
    store.connect(edge);
    const state = useWorkflowStore.getState();
    if (!state.document) return;
    const report = await api<{ errors: { message: string }[] }>(
      `/workflows/${state.document.id}/validate`,
      {
        method: "POST",
        body: JSON.stringify(toDocument(state, viewport.current)),
      },
    );
    if (report.errors.length) {
      store.undo();
      setError(report.errors[0].message);
    }
  };

  const selectNodes = (nodes: FlowNode[]) => {
    const updateHints = (next: string[]) => {
      setColumnHints((current) => {
        if (
          current.length === next.length &&
          current.every((value, index) => value === next[index])
        )
          return current;
        return next;
      });
    };
    const ids = nodes.map((node) => node.id);
    store.setSelected(ids);
    const document = store.document;
    if (!document || ids.length !== 1) {
      updateHints([]);
      return;
    }
    void api<Record<string, string[]>>(
      `/workflows/${document.id}/nodes/${ids[0]}/column-hints`,
      { method: "POST" },
    )
      .then((hints) => {
        updateHints(Object.values(hints).flat());
      })
      .catch(() => {
        updateHints([]);
      });
  };

  const execute = useCallback(
    async (scope: Record<string, unknown> = { kind: "all", node_id: null }) => {
      const document = useWorkflowStore.getState().document;
      if (!document) return;
      await save();
      try {
        const resources = await api<{
          missing: { message: string }[];
        }>(`/workflows/${document.id}/resources/preflight`);
        const allowMissing = resources.missing.length
          ? window.confirm(
              `外部资源缺失：\n${resources.missing.map((item) => item.message).join("\n")}\n仍要运行？`,
            )
          : false;
        if (resources.missing.length && !allowMissing) return;
        const result = await api<{ run_id: string }>(
          `/workflows/${document.id}/runs`,
          {
            method: "POST",
            body: JSON.stringify({
              scope,
              allow_missing_resources: allowMissing,
            }),
          },
        );
        useRunStore.getState().started(result.run_id);
        const snapshot = await api<{
          nodes: Record<
            string,
            { status: string; error?: { message: string; traceback?: string } }
          >;
        }>(`/runs/${result.run_id}`);
        useRunStore.getState().snapshot(snapshot);
        setMenu(null);
      } catch (reason) {
        setError(String(reason));
      }
    },
    [save],
  );

  useEffect(() => {
    const listener = () => {
      const selected = useWorkflowStore.getState().selected[0];
      if (selected) void execute({ kind: "to_node", node_id: selected });
    };
    window.addEventListener("weft-execute-to", listener);
    return () => {
      window.removeEventListener("weft-execute-to", listener);
    };
  }, [store.selected, execute]);

  const selectedNode = store.nodes.find((node) =>
    store.selected.includes(node.id),
  );
  const variableNames = [
    ...(store.document?.variables.map((variable) => variable.name) ?? []),
    ...store.nodes.flatMap((node) => {
      if (node.data.type !== "flow.variable") return [];
      const values = node.data.params.values;
      if (!Array.isArray(values)) return [];
      return values.flatMap((value) => {
        if (typeof value !== "object" || value === null || !("name" in value))
          return [];
        const name: unknown = (value as { name?: unknown }).name;
        return typeof name === "string" ? [name] : [];
      });
    }),
  ];
  const displayNodes = store.nodes.map((node) => ({
    ...node,
    data: {
      ...node.data,
      status: run.statuses[node.id] ?? node.data.status,
      error: run.errors[node.id],
      iteration: run.iterations[node.id],
      workflowId: store.document?.id,
    },
  }));

  return (
    <main className="editor-shell">
      <header className="toolbar">
        <strong>Weft</strong>
        <input
          aria-label="工作流名称"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
        <input
          aria-label="父目录"
          value={parent}
          onChange={(event) => {
            setParent(event.target.value);
          }}
        />
        <button onClick={() => void create()}>新建工作流</button>
        <button onClick={() => void open()}>打开工作流</button>
        <button onClick={() => void importWorkflow()}>导入工作流</button>
        {store.document && (
          <button onClick={() => void pack()}>打包工作流</button>
        )}
        <button
          onClick={() => {
            setSettingsOpen(true);
          }}
        >
          设置
        </button>
        {store.document && (
          <button
            onClick={() => {
              setChatOpen(true);
            }}
          >
            聊天
          </button>
        )}
        {store.document && (
          <span>
            {store.document.name}
            {store.dirty ? " *" : ""}
          </span>
        )}
        {breadcrumbs.length > 0 && (
          <nav aria-label="Metanode 面包屑">
            {store.document?.name} &gt;{" "}
            {breadcrumbs.map((item) => item.name).join(" > ")}
            <button onClick={leaveMetanode}>返回上级</button>
          </nav>
        )}
        {store.selected.length > 0 && (
          <button onClick={collapse}>折叠为 Metanode</button>
        )}
        <button onClick={() => void save()}>保存</button>
        <button onClick={() => void execute()}>运行</button>
        {run.runId && (
          <button
            onClick={() => {
              void api(`/runs/${run.runId}/cancel`, { method: "POST" });
            }}
          >
            停止
          </button>
        )}
      </header>
      {serverWarning && <div role="alert">{serverWarning}</div>}
      {error && (
        <div role="alert" className="error-banner">
          {error}
        </div>
      )}
      {pathIssues.length > 0 && (
        <section aria-label="绝对路径警告">
          {pathIssues.map((issue) => (
            <button
              key={`${issue.node_id}:${issue.param}`}
              onClick={() => {
                store.setSelected([issue.node_id]);
                const node = store.nodes.find(
                  (item) => item.id === issue.node_id,
                );
                if (node) void flow.fitView({ nodes: [node] });
              }}
            >
              定位 {issue.node_id}.{issue.param}：{issue.value}
            </button>
          ))}
        </section>
      )}
      <div className="editor-body">
        <NodePanel types={store.nodeTypes} onAdd={addAtCenter} />
        <section className="canvas" aria-label="工作流画布">
          <ReactFlow
            nodes={displayNodes}
            edges={store.edges}
            nodeTypes={{ weft: WeftNode, note: CanvasNote }}
            onPaneContextMenu={(event) => {
              event.preventDefault();
              store.addNote(
                flow.screenToFlowPosition({
                  x: event.clientX,
                  y: event.clientY,
                }),
              );
            }}
            onNodesChange={(changes: NodeChange<FlowNode>[]) => {
              store.moveNodes(applyNodeChanges(changes, store.nodes));
            }}
            onConnect={(connection) => void connect(connection)}
            onNodeDoubleClick={(_, node) => {
              enterMetanode(node);
            }}
            onNodeContextMenu={(event, node) => {
              event.preventDefault();
              setMenu({ nodeId: node.id, x: event.clientX, y: event.clientY });
            }}
            onSelectionChange={({ nodes }) => {
              selectNodes(nodes);
            }}
            onMoveEnd={(_, value) => {
              viewport.current = value;
            }}
            onDrop={(event) => {
              event.preventDefault();
              const type = event.dataTransfer.getData("application/weft-node");
              if (type)
                store.addNode(
                  type,
                  flow.screenToFlowPosition({
                    x: event.clientX,
                    y: event.clientY,
                  }),
                );
            }}
            onDragOver={(event) => {
              event.preventDefault();
            }}
            minZoom={0.25}
            maxZoom={2}
            fitView
          >
            <Background />
            <MiniMap />
            <Controls />
          </ReactFlow>
        </section>
        <aside className="inspector">
          {selectedNode && (
            <SchemaForm
              node={selectedNode.data}
              declaration={nodeTypes.get(selectedNode.data.type)}
              root={root}
              columnHints={columnHints}
              variables={variableNames}
              onChange={(params) => {
                store.updateParams(selectedNode.id, params);
              }}
              onCommentChange={(comment) => {
                store.updateComment(selectedNode.id, comment);
              }}
            />
          )}
          {selectedNode?.data.type === "flow.trigger" && (
            <TriggerStatusPanel
              workflowId={store.document?.id ?? ""}
              params={selectedNode.data.params}
            />
          )}
          {selectedNode && (
            <TracePanel entries={run.traces[selectedNode.id] ?? []} />
          )}
          {selectedNode && <AuditPanel runId={run.runId} />}
          {selectedNode && run.runId && <ChangeReviewPanel runId={run.runId} />}
          {selectedNode && Object.hasOwn(run.errors, selectedNode.id) && (
            <pre className="error-details">
              {JSON.stringify(run.errors[selectedNode.id], null, 2)}
            </pre>
          )}
        </aside>
      </div>
      <LogPanel />
      {store.document && (
        <HistoryPanel
          workflowId={store.document.id}
          onPreview={(runId, nodeId, port) => {
            setPreview({ runId, nodeId, port });
          }}
        />
      )}
      {menu && (
        <div className="context-menu" style={{ left: menu.x, top: menu.y }}>
          <button
            onClick={() =>
              void execute({ kind: "to_node", node_id: menu.nodeId })
            }
          >
            执行到此
          </button>
          <button
            onClick={() =>
              void execute({ kind: "from_node", node_id: menu.nodeId })
            }
          >
            从此开始
          </button>
          <button
            onClick={() =>
              void execute({ kind: "single", node_id: menu.nodeId })
            }
          >
            仅执行本节点
          </button>
          {store.nodes.find((node) => node.id === menu.nodeId)?.data.type ===
            "flow.metanode" && (
            <button
              onClick={() => {
                expand(menu.nodeId);
              }}
            >
              展开 Metanode
            </button>
          )}
          <button
            onClick={() => {
              void api(
                `/workflows/${store.document?.id ?? ""}/nodes/${menu.nodeId}/reset`,
                { method: "POST" },
              );
              run.reset();
              setMenu(null);
            }}
          >
            重置
          </button>
        </div>
      )}
      {run.runId && <ConfirmPanel runId={run.runId} />}
      {chatOpen && store.document && (
        <ChatPanel
          workflowId={store.document.id}
          enabled={Boolean(
            (
              store.document.nodes.find((node) => node.type === "flow.trigger")
                ?.params.chat as { enabled?: boolean } | undefined
            )?.enabled,
          )}
          onClose={() => {
            setChatOpen(false);
          }}
        />
      )}
      {settingsOpen && (
        <SettingsPanel
          onClose={() => {
            setSettingsOpen(false);
          }}
        />
      )}
      {preview && store.document && (
        <PortView
          workflowId={store.document.id}
          runId={preview.runId ?? run.runId}
          nodeId={preview.nodeId}
          port={preview.port}
          onClose={() => {
            setPreview(null);
          }}
        />
      )}
    </main>
  );
}

export function App() {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  );
}
