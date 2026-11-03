import { useState } from "react";
import { api } from "../api/client";

interface Change {
  path: string;
  rel_root: string | null;
  kind: string;
  size: number;
  is_text: boolean;
  protected: boolean;
  baseline_hash: string | null;
  state: string;
  error: string | null;
}
interface ChangeSet {
  changes: Change[];
  audit_complete: boolean;
  audit_warnings: string[];
}

export function ChangeReviewPanel({ runId }: { runId: string }) {
  const [changes, setChanges] = useState<Change[]>([]);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [diff, setDiff] = useState("");
  const [complete, setComplete] = useState(true);
  const [notice, setNotice] = useState("");
  const load = async () => {
    const result = await api<ChangeSet>(`/runs/${runId}/changes`);
    setChanges(result.changes);
    setComplete(result.audit_complete);
    setNotice(result.audit_warnings.join("\n"));
  };
  const apply = async (overwrite: boolean) => {
    const result = await api<{ results: Change[] }>(
      `/runs/${runId}/changes/apply`,
      {
        method: "POST",
        body: JSON.stringify({
          paths: selected,
          overwrite_conflicts: overwrite,
        }),
      },
    );
    setNotice(
      result.results.some((change) => change.state === "conflict")
        ? "部分文件已被外部修改；请查看 diff 后显式覆盖"
        : "变更已处理",
    );
    await load();
  };
  const group = (external: boolean) =>
    changes.filter((change) => (change.rel_root === null) === external);
  return (
    <section aria-label="变更审批">
      <button
        onClick={() => {
          setOpen(true);
          void load().catch((reason: unknown) => {
            setNotice(String(reason));
          });
        }}
      >
        变更审批
      </button>
      {open && (
        <div>
          {!complete && <p role="alert">审计不完整</p>}
          {[false, true].map((external) => (
            <section key={String(external)}>
              <h4>{external ? "Root 外" : "Root 内"}</h4>
              {group(external).map((change) => (
                <div key={change.path}>
                  <input
                    type="checkbox"
                    aria-label={`选择 ${change.path}`}
                    disabled={change.protected || change.state === "applied"}
                    checked={selected.includes(change.path)}
                    onChange={(event) => {
                      setSelected(
                        event.target.checked
                          ? [...selected, change.path]
                          : selected.filter((path) => path !== change.path),
                      );
                    }}
                  />
                  <span>
                    {change.kind} {change.path}（{change.size} 字节，
                    {change.state}）
                  </span>
                  <button
                    onClick={() => {
                      void api<{ diff: string }>(
                        `/runs/${runId}/changes/diff?path=${encodeURIComponent(change.path)}`,
                      ).then((result) => {
                        setDiff(result.diff);
                      });
                    }}
                  >
                    查看 diff
                  </button>
                  {change.error && <span>{change.error}</span>}
                </div>
              ))}
            </section>
          ))}
          <pre>{diff}</pre>
          <button disabled={!selected.length} onClick={() => void apply(false)}>
            应用所选
          </button>
          <button disabled={!selected.length} onClick={() => void apply(true)}>
            显式覆盖冲突
          </button>
          <button
            onClick={() => {
              void api(`/runs/${runId}/changes/discard`, {
                method: "POST",
                body: JSON.stringify({
                  paths: selected.length ? selected : null,
                }),
              }).then(() => load());
            }}
          >
            丢弃变更
          </button>
          <p role="status">{notice}</p>
        </div>
      )}
    </section>
  );
}
