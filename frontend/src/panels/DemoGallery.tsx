import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Icon } from "../components/Icon";

export interface DemoInfo {
  id: string;
  title: string;
  description: string;
  requirements: string;
}

export function DemoGallery({
  parent,
  onClose,
  onCreate,
}: {
  parent: string;
  onClose: () => void;
  onCreate: (demoId: string, name: string, parentDir: string) => Promise<void>;
}) {
  const [demos, setDemos] = useState<DemoInfo[]>([]);
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [parentDir, setParentDir] = useState(parent);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    void api<DemoInfo[]>("/demos")
      .then((items) => {
        setDemos(items);
        setSelected(items[0]?.id ?? "");
        setName(items[0]?.id ?? "");
      })
      .catch((reason: unknown) => {
        setError(String(reason));
      });
  }, []);

  const create = async () => {
    if (!selected || !name || !parentDir) return;
    setCreating(true);
    setError("");
    try {
      await onCreate(selected, name, parentDir);
    } catch (reason) {
      setError(String(reason));
      setCreating(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-label="示例工作流">
      <section className="modal demo-modal">
        <header className="modal-header">
          <div>
            <span className="dialog-icon">
              <Icon name="grid" />
            </span>
            <div>
              <h2>从一个示例开始</h2>
              <p>创建独立副本，对副本的修改不会影响内置示例</p>
            </div>
          </div>
          <button className="icon-button" aria-label="关闭" onClick={onClose}>
            <Icon name="close" />
          </button>
        </header>
        <div className="demo-list">
          {demos.map((demo) => (
            <button
              className={`demo-card ${selected === demo.id ? "selected" : ""}`}
              key={demo.id}
              onClick={() => {
                setSelected(demo.id);
                setName(demo.id);
              }}
            >
              <span className="demo-card-icon">
                <Icon name={demo.id === "llm-text" ? "agent" : "table"} />
              </span>
              <span>
                <strong>{demo.title}</strong>
                <span>{demo.description}</span>
                <small>{demo.requirements}</small>
              </span>
            </button>
          ))}
        </div>
        <div className="demo-destination">
          <label className="inline-field">
            <span>工作流名称</span>
            <input
              aria-label="示例名称"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </label>
          <label className="inline-field">
            <span>保存到</span>
            <input
              aria-label="示例父目录"
              value={parentDir}
              onChange={(event) => {
                setParentDir(event.target.value);
              }}
            />
          </label>
        </div>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        <footer className="modal-footer">
          <span>CSV 与表格示例可直接运行；LLM 示例请按画布便签完成配置。</span>
          <div>
            <button className="button secondary" onClick={onClose}>
              取消
            </button>
            <button
              className="button primary"
              disabled={!selected || !name || !parentDir || creating}
              onClick={() => void create()}
            >
              <Icon name="play" />
              {creating ? "创建中…" : "创建并打开"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
