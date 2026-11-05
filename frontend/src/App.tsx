import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  SelectionMode,
  applyNodeChanges,
  useReactFlow,
  useUpdateNodeInternals,
} from "@xyflow/react";
import type { NodeChange } from "@xyflow/react";
import { api, formatApiError } from "./api/client";
import { useEditorShortcuts } from "./editorShortcuts";
import { Icon, nodeVisual } from "./components/Icon";
import { ConnectionIndicator } from "./components/ConnectionIndicator";
import { OverlayHost } from "./components/OverlayHost";
import { AuditPanel } from "./panels/AuditPanel";
import { DemoGallery } from "./panels/DemoGallery";
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
import { useWorkflowStore } from "./stores/workflowStore";
import type { FlowNode } from "./stores/workflowStore";
import type { NodeTypeDecl } from "./types/workflow";
import { useCanvasInteractions } from "./hooks/useCanvasInteractions";
import { useWorkflowCommands } from "./hooks/useWorkflowCommands";
import type { PathIssue } from "./hooks/useWorkflowCommands";
import { useWorkflowDocument } from "./hooks/useWorkflowDocument";
import { useOverlayHost } from "./hooks/useOverlayHost";
import "@xyflow/react/dist/style.css";
import "./styles.css";

type Overlay = "demos" | "chat" | "settings" | "preview";

function NodeInternalsSync({ nodes }: { nodes: FlowNode[] }) {
  const updateNodeInternals = useUpdateNodeInternals();
  useEffect(() => {
    updateNodeInternals(nodes.map((node) => node.id));
  }, [nodes, updateNodeInternals]);
  return null;
}

function Editor() {
  const store = useWorkflowStore();
  const run = useRunStore();
  const [preview, setPreview] = useState<{
    nodeId: string;
    port: string;
    runId?: string;
  } | null>(null);
  const setNodeTypes = useWorkflowStore((state) => state.setNodeTypes);
  const [error, setError] = useState("");
  const [serverWarning, setServerWarning] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [demosOpen, setDemosOpen] = useState(false);
  const [name, setName] = useState("weekly");
  const [parent, setParent] = useState("C:/flows");
  const [root, setRoot] = useState("");
  const [pathIssues, setPathIssues] = useState<PathIssue[]>([]);
  const flow = useReactFlow<FlowNode>();
  const canvasRef = useRef<HTMLElement | null>(null);
  const overlayFocus = useRef<Partial<Record<Overlay, HTMLElement | null>>>({});
  const nodeTypes = useMemo(
    () => new Map(store.nodeTypes.map((item) => [item.type, item])),
    [store.nodeTypes],
  );
  const {
    save,
    load,
    reload,
    revisionConflict,
    viewport,
    graphStack,
    breadcrumbs,
    setBreadcrumbs,
  } = useWorkflowDocument({ setError });
  const { request: overlayRequest, form, confirm, message } = useOverlayHost();
  const dialogs = useMemo(
    () => ({ form, confirm, message }),
    [form, confirm, message],
  );
  const {
    menu,
    setMenu,
    columnHints,
    collapse,
    expand,
    enterMetanode,
    leaveMetanode,
    addAtCenter,
    connect,
    selectNodes,
  } = useCanvasInteractions({
    flow,
    viewport,
    graphStack,
    setBreadcrumbs,
    setError,
  });

  const openOverlay = useCallback((overlay: Exclude<Overlay, "preview">) => {
    const active = document.activeElement;
    overlayFocus.current[overlay] =
      active instanceof HTMLElement ? active : null;
    if (overlay === "demos") setDemosOpen(true);
    if (overlay === "chat") setChatOpen(true);
    if (overlay === "settings") setSettingsOpen(true);
  }, []);

  const openPreview = useCallback(
    (next: { nodeId: string; port: string; runId?: string }) => {
      const active = document.activeElement;
      overlayFocus.current.preview =
        active instanceof HTMLElement ? active : null;
      setPreview(next);
    },
    [],
  );

  const closeOverlay = useCallback((overlay: Overlay) => {
    if (overlay === "demos") setDemosOpen(false);
    if (overlay === "chat") setChatOpen(false);
    if (overlay === "settings") setSettingsOpen(false);
    if (overlay === "preview") setPreview(null);
    const target = overlayFocus.current[overlay];
    overlayFocus.current[overlay] = null;
    if (target?.isConnected) target.focus();
  }, []);

  const { create, createDemo, open, importWorkflow, pack } =
    useWorkflowCommands({
      name,
      parent,
      setName,
      setParent,
      setRoot,
      setError,
      setPathIssues,
      load,
      closeDemos: () => {
        closeOverlay("demos");
      },
      dialogs,
    });

  useEffect(() => {
    void api<NodeTypeDecl[]>("/nodes/types")
      .then((types) => {
        setNodeTypes(types);
      })
      .catch((reason: unknown) => {
        setError(formatApiError(reason));
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
      openPreview(detail);
    };
    window.addEventListener("weft-preview", listener);
    return () => {
      window.removeEventListener("weft-preview", listener);
    };
  }, [openPreview]);

  useEditorShortcuts({
    save: () => {
      void save();
    },
    undo: () => {
      useWorkflowStore.getState().undo();
    },
    redo: () => {
      useWorkflowStore.getState().redo();
    },
    copy: () => {
      useWorkflowStore.getState().copy();
    },
    paste: () => {
      useWorkflowStore.getState().paste();
    },
    deleteSelected: () => {
      useWorkflowStore.getState().deleteSelected();
    },
    fitView: () => {
      void flow.fitView();
    },
    fitSelected: () => {
      const selected = useWorkflowStore
        .getState()
        .nodes.filter((node) => node.selected);
      if (selected.length) void flow.fitView({ nodes: selected });
    },
    escape: () => {
      if (document.querySelector('[role="alertdialog"]')) return true;
      if (preview && store.document) {
        closeOverlay("preview");
        return true;
      }
      if (settingsOpen) {
        closeOverlay("settings");
        return true;
      }
      if (demosOpen) {
        closeOverlay("demos");
        return true;
      }
      if (chatOpen && store.document) {
        closeOverlay("chat");
        return true;
      }
      if (menu) {
        setMenu(null);
        const node = document.querySelector(`[data-id="${menu.nodeId}"]`);
        if (node instanceof HTMLElement) node.focus();
        else canvasRef.current?.focus();
        return true;
      }
      const state = useWorkflowStore.getState();
      if (!state.selected.length && !state.nodes.some((node) => node.selected))
        return false;
      state.moveNodes(
        state.nodes.map((node) =>
          node.selected ? { ...node, selected: false } : node,
        ),
      );
      state.setSelected([]);
      canvasRef.current?.focus();
      return true;
    },
  });

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
          ? await confirm({
              title: "外部资源缺失",
              message: `外部资源缺失：\n${resources.missing.map((item) => item.message).join("\n")}\n仍要运行？`,
              confirmLabel: "仍要运行",
            })
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
        setError(formatApiError(reason));
      }
    },
    [confirm, save, setMenu],
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
      <aside className="app-rail" aria-label="工作流工具">
        <img className="brand-mark" src="/weft-mark.svg" alt="" />
        <nav className="rail-nav" aria-label="工作流操作">
          <button
            className="rail-button"
            aria-label="示例工作流"
            data-tooltip="示例工作流"
            onClick={() => {
              openOverlay("demos");
            }}
          >
            <Icon name="grid" />
          </button>
          <button
            className="rail-button"
            aria-label="打开工作流"
            data-tooltip="打开工作流"
            onClick={() => void open()}
          >
            <Icon name="open" />
          </button>
          <button
            className="rail-button"
            aria-label="导入工作流"
            data-tooltip="导入工作流"
            onClick={() => void importWorkflow()}
          >
            <Icon name="import" />
          </button>
          {store.document && (
            <button
              className="rail-button"
              aria-label="打包工作流"
              data-tooltip="打包工作流"
              onClick={() => void pack()}
            >
              <Icon name="package" />
            </button>
          )}
          {store.document && (
            <button
              className="rail-button"
              aria-label="聊天"
              data-tooltip="聊天"
              onClick={() => {
                openOverlay("chat");
              }}
            >
              <Icon name="send" />
            </button>
          )}
        </nav>
        <div className="rail-bottom">
          <button
            className="rail-button"
            aria-label="设置"
            data-tooltip="设置"
            onClick={() => {
              openOverlay("settings");
            }}
          >
            <Icon name="settings" />
          </button>
        </div>
      </aside>
      <div className="app-shell">
        <header className="toolbar">
          <div className="brand-lockup">
            <img src="/weft-logo.svg" alt="Weft" />
            <span>LOCAL WORKFLOW</span>
          </div>
          <div className="workflow-create">
            <label className="compact-field">
              <span>名称</span>
              <input
                aria-label="工作流名称"
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
              />
            </label>
            <label className="compact-field parent-field">
              <span>位置</span>
              <input
                aria-label="父目录"
                value={parent}
                onChange={(event) => {
                  setParent(event.target.value);
                }}
              />
            </label>
            <button className="button secondary" onClick={() => void create()}>
              <Icon name="plus" />
              新建工作流
            </button>
          </div>
          <div className="toolbar-actions">
            <ConnectionIndicator />
            {store.document && (
              <span className="workflow-identity" title="当前工作流">
                <Icon name="flow" />
                <span>
                  {store.document.name}
                  {store.dirty ? " *" : ""}
                </span>
              </span>
            )}
            {breadcrumbs.length > 0 && (
              <nav className="breadcrumbs" aria-label="Metanode 面包屑">
                {store.document?.name} &gt;{" "}
                {breadcrumbs.map((item) => item.name).join(" > ")}
                <button className="text-button" onClick={leaveMetanode}>
                  返回上级
                </button>
              </nav>
            )}
            {store.selected.length > 0 && (
              <button
                className="button ghost collapse-action"
                onClick={collapse}
              >
                <Icon name="grid" />
                折叠为 Metanode
              </button>
            )}
            <button className="button secondary" onClick={() => void save()}>
              <Icon name="save" />
              保存
            </button>
            <button className="button primary" onClick={() => void execute()}>
              <Icon name="play" />
              运行
            </button>
            {run.runId && (
              <button
                className="button danger-subtle"
                onClick={() => {
                  void api(`/runs/${run.runId}/cancel`, { method: "POST" });
                }}
              >
                <Icon name="stop" />
                停止
              </button>
            )}
          </div>
        </header>
        {serverWarning && (
          <div className="error-banner" role="alert">
            <Icon name="warn" />
            {serverWarning}
          </div>
        )}
        {(error || revisionConflict) && (
          <div className="error-banner" role="alert">
            <Icon name="warn" />
            <span>{error || "工作流保存冲突（REVISION_CONFLICT）"}</span>
            {revisionConflict && (
              <button
                className="button secondary"
                onClick={() => void reload()}
              >
                重新读取
              </button>
            )}
          </div>
        )}
        {pathIssues.length > 0 && (
          <section className="path-issues" aria-label="绝对路径警告">
            <Icon name="warn" />
            <div>
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
            </div>
          </section>
        )}
        <div className="editor-body">
          <NodePanel types={store.nodeTypes} onAdd={addAtCenter} />
          <div className="canvas-column">
            <section
              className="canvas"
              aria-label="工作流画布"
              ref={canvasRef}
              tabIndex={-1}
            >
              <div className="canvas-caption">
                <span className="canvas-mode">
                  <Icon name="flow" />
                  设计
                </span>
                <span>左键框选 · 中键平移 · 右键添加便签</span>
              </div>
              <ReactFlow
                nodes={displayNodes}
                edges={store.edges}
                nodeTypes={{ weft: WeftNode, note: CanvasNote }}
                deleteKeyCode={null}
                panOnDrag={[1]}
                selectionOnDrag
                selectionMode={SelectionMode.Partial}
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
                  setMenu({
                    nodeId: node.id,
                    x: event.clientX,
                    y: event.clientY,
                  });
                }}
                onSelectionChange={({ nodes }) => {
                  selectNodes(nodes);
                }}
                onMoveEnd={(_, value) => {
                  viewport.current = value;
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  const type = event.dataTransfer.getData(
                    "application/weft-node",
                  );
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
                fitViewOptions={{ maxZoom: 1 }}
              >
                <NodeInternalsSync nodes={store.nodes} />
                <Background color="#d4d1dc" gap={18} size={1} />
                <MiniMap />
                <Controls />
              </ReactFlow>
            </section>
            <LogPanel />
            {store.document && (
              <HistoryPanel
                workflowId={store.document.id}
                onPreview={(runId, nodeId, port) => {
                  openPreview({ runId, nodeId, port });
                }}
              />
            )}
          </div>
          <aside className="inspector">
            <div className="inspector-heading">
              {selectedNode ? (
                <>
                  <span
                    className={`palette-icon ${nodeVisual(selectedNode.data.type).tone}`}
                  >
                    <Icon name={nodeVisual(selectedNode.data.type).icon} />
                  </span>
                  <div>
                    <h2>{selectedNode.data.name}</h2>
                    <span>{selectedNode.data.type}</span>
                  </div>
                </>
              ) : (
                <>
                  <span className="palette-icon flow">
                    <Icon name="settings" />
                  </span>
                  <div>
                    <h2>节点配置</h2>
                    <span>检查器</span>
                  </div>
                </>
              )}
            </div>
            <div className="inspector-content">
              {selectedNode ? (
                <>
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
                  {selectedNode.data.type === "flow.trigger" && (
                    <TriggerStatusPanel
                      workflowId={store.document?.id ?? ""}
                      params={selectedNode.data.params}
                    />
                  )}
                  <TracePanel entries={run.traces[selectedNode.id] ?? []} />
                  <AuditPanel runId={run.runId} />
                  {run.runId && <ChangeReviewPanel runId={run.runId} />}
                  {Object.hasOwn(run.errors, selectedNode.id) && (
                    <pre className="error-details">
                      {JSON.stringify(run.errors[selectedNode.id], null, 2)}
                    </pre>
                  )}
                </>
              ) : (
                <div className="empty-state">
                  <span className="empty-state-icon">
                    <Icon name="flow" />
                  </span>
                  <h3>选择一个节点</h3>
                  <p>查看并编辑节点参数、运行轨迹与审计信息。</p>
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
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
      {demosOpen && (
        <DemoGallery
          parent={parent}
          onClose={() => {
            closeOverlay("demos");
          }}
          onCreate={createDemo}
        />
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
            closeOverlay("chat");
          }}
        />
      )}
      {settingsOpen && (
        <SettingsPanel
          onClose={() => {
            closeOverlay("settings");
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
            closeOverlay("preview");
          }}
        />
      )}
      <OverlayHost request={overlayRequest} />
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
