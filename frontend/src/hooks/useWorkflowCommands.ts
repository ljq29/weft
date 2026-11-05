import { useCallback } from "react";
import { api, formatApiError } from "../api/client";
import { useWorkflowStore } from "../stores/workflowStore";
import type { WorkflowDocument } from "../types/workflow";
import type { useOverlayHost } from "./useOverlayHost";

export interface PathIssue {
  node_id: string;
  param: string;
  value: string;
}

type LoadedDocument = WorkflowDocument & {
  nodes: unknown[];
  edges: unknown[];
};

interface WorkflowCommandsOptions {
  name: string;
  parent: string;
  setName: (name: string) => void;
  setParent: (parent: string) => void;
  setRoot: (root: string) => void;
  setError: (error: string) => void;
  setPathIssues: (issues: PathIssue[]) => void;
  load: (document: LoadedDocument) => void;
  closeDemos: () => void;
  dialogs: Pick<
    ReturnType<typeof useOverlayHost>,
    "form" | "confirm" | "message"
  >;
}

async function fetchWorkflow(id: string) {
  return api<LoadedDocument>(`/workflows/${id}`);
}

export function useWorkflowCommands({
  name,
  parent,
  setName,
  setParent,
  setRoot,
  setError,
  setPathIssues,
  load,
  closeDemos,
  dialogs,
}: WorkflowCommandsOptions) {
  const create = useCallback(async () => {
    try {
      const result = await api<{ id: string; path: string }>("/workflows", {
        method: "POST",
        body: JSON.stringify({ name, parent_dir: parent }),
      });
      setRoot(result.path);
      load(await fetchWorkflow(result.id));
      setError("");
    } catch (reason) {
      setError(formatApiError(reason));
    }
  }, [load, name, parent, setError, setRoot]);

  const createDemo = useCallback(
    async (demoId: string, demoName: string, parentDir: string) => {
      const result = await api<{ id: string; path: string }>(
        `/demos/${demoId}/create`,
        {
          method: "POST",
          body: JSON.stringify({ name: demoName, parent_dir: parentDir }),
        },
      );
      setRoot(result.path);
      setName(demoName);
      setParent(parentDir);
      load(await fetchWorkflow(result.id));
      closeDemos();
      setError("");
    },
    [closeDemos, load, setError, setName, setParent, setRoot],
  );

  const open = useCallback(async () => {
    const values = await dialogs.form(
      "打开工作流",
      [{ name: "path", label: "工作流目录" }],
      "打开",
    );
    if (!values) return;
    try {
      const result = await api<{ id: string; path: string }>(
        "/workflows/open",
        {
          method: "POST",
          body: JSON.stringify({ path: values.path }),
        },
      );
      setRoot(result.path);
      load(await fetchWorkflow(result.id));
      setError("");
    } catch (reason) {
      setError(formatApiError(reason));
    }
  }, [dialogs, load, setError, setRoot]);

  const importWorkflow = useCallback(async () => {
    const values = await dialogs.form(
      "导入工作流",
      [
        { name: "zipPath", label: "工作流 zip 路径" },
        {
          name: "destDir",
          label: "导入目标父目录",
          defaultValue: parent,
        },
      ],
      "导入",
    );
    if (!values) return;
    try {
      const result = await api<{ id: string; path: string }>(
        "/workflows/unpack",
        {
          method: "POST",
          body: JSON.stringify({
            zip_path: values.zipPath,
            dest_dir: values.destDir,
          }),
        },
      );
      setRoot(result.path);
      load(await fetchWorkflow(result.id));
      setError("");
    } catch (reason) {
      setError(formatApiError(reason));
    }
  }, [dialogs, load, parent, setError, setRoot]);

  const pack = useCallback(async () => {
    const document = useWorkflowStore.getState().document;
    if (!document) return;
    try {
      const report = await api<{
        errors: { message: string }[];
        warnings: { message: string }[];
        abs_paths: PathIssue[];
        size_estimate: number;
      }>(`/workflows/${document.id}/pack/preflight`);
      setPathIssues(report.abs_paths);
      if (report.errors.length) {
        setError(report.errors.map((item) => item.message).join("\n"));
        return;
      }
      if (report.warnings.length) {
        const summary = report.warnings.map((item) => item.message).join("\n");
        const proceed = await dialogs.confirm({
          title: "打包警告",
          message: `发现打包警告：\n${summary}\n是否继续？`,
          confirmLabel: "继续打包",
        });
        if (!proceed) return;
      }
      const excludeData = await dialogs.confirm({
        title: "打包数据目录",
        message: "是否排除 data/ 数据目录？",
        confirmLabel: "排除 data",
        cancelLabel: "保留 data",
      });
      const result = await api<{ path: string }>(
        `/workflows/${document.id}/pack`,
        {
          method: "POST",
          body: JSON.stringify({
            exclude_data: excludeData,
            confirm_warnings: true,
          }),
        },
      );
      setError("");
      await dialogs.message("打包完成", `打包完成：${result.path}`);
    } catch (reason) {
      setError(formatApiError(reason));
    }
  }, [dialogs, setError, setPathIssues]);

  return { create, createDemo, open, importWorkflow, pack };
}
