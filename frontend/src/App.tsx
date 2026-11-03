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
import { connectRuns } from "./api/ws";
import { LogPanel } from "./panels/LogPanel";
import { PortView } from "./panels/PortView";
import { NodePanel } from "./panels/NodePanel";
import { SchemaForm } from "./panels/SchemaForm";
import { SettingsPanel } from "./panels/SettingsPanel";
import { TracePanel } from "./panels/TracePanel";
import { ChatPanel } from "./panels/ChatPanel";
import { useRunStore } from "./stores/runStore";
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
  } | null>(null);
  const [menu, setMenu] = useState<{
    nodeId: string;
    x: number;
    y: number;
  } | null>(null);
  const setNodeTypes = useWorkflowStore((state) => state.setNodeTypes);
  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [name, setName] = useState("weekly");
  const [parent, setParent] = useState("C:/flows");
  const [root, setRoot] = useState("");
  const [columnHints, setColumnHints] = useState<string[]>([]);
  const flow = useReactFlow();
  const viewport = useRef({ x: 0, y: 0, zoom: 1 });
  const nodeTypes = useMemo(
    () => new Map(store.nodeTypes.map((item) => [item.type, item])),
    [store.nodeTypes],
  );

  const save = useCallback(() => {
    const operation = saveQueue.then(async () => {
      const state = useWorkflowStore.getState();
      if (!state.document) return;
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
    const nodes = document.nodes.map((raw) => {
      const node = raw as StoredNode;
      return {
        id: node.id,
        type: "weft",
        position: node.position,
        data: {
          nodeId: node.id,
          type: node.type,
          name: node.name,
          params: node.params,
          inputs: nodeTypes.get(node.type)?.inputs ?? [],
          outputs: nodeTypes.get(node.type)?.outputs ?? [],
          comment: node.comment ?? "",
          status: "configured",
        },
      };
    });
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
    store.setDocument(document, nodes, edges);
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
        const result = await api<{ run_id: string }>(
          `/workflows/${document.id}/runs`,
          { method: "POST", body: JSON.stringify({ scope }) },
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
      {error && (
        <div role="alert" className="error-banner">
          {error}
        </div>
      )}
      <div className="editor-body">
        <NodePanel types={store.nodeTypes} onAdd={addAtCenter} />
        <section className="canvas" aria-label="工作流画布">
          <ReactFlow
            nodes={displayNodes}
            edges={store.edges}
            nodeTypes={{ weft: WeftNode }}
            onNodesChange={(changes: NodeChange<FlowNode>[]) => {
              store.moveNodes(applyNodeChanges(changes, store.nodes));
            }}
            onConnect={(connection) => void connect(connection)}
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
            />
          )}
          {selectedNode && (
            <TracePanel entries={run.traces[selectedNode.id] ?? []} />
          )}
          {selectedNode && <AuditPanel runId={run.runId} />}
          {selectedNode && Object.hasOwn(run.errors, selectedNode.id) && (
            <pre className="error-details">
              {JSON.stringify(run.errors[selectedNode.id], null, 2)}
            </pre>
          )}
        </aside>
      </div>
      <LogPanel />
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
          runId={run.runId}
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
