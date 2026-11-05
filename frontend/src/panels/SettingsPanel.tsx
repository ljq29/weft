import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Icon } from "../components/Icon";

interface LLMConfig {
  base_url: string;
  api_key: string;
  model: string;
  timeout: number;
  extra_headers: Record<string, string>;
}

const emptyConfig: LLMConfig = {
  base_url: "",
  api_key: "",
  model: "",
  timeout: 120,
  extra_headers: {},
};

export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [configs, setConfigs] = useState<Record<string, LLMConfig>>({});
  const [selected, setSelected] = useState("");
  const [headers, setHeaders] = useState("{}");
  const [message, setMessage] = useState("");
  const [cache, setCache] = useState<Record<string, unknown>>({});
  const [advanced, setAdvanced] = useState("{}");
  useEffect(() => {
    void api<{
      llm?: Record<string, LLMConfig>;
      cache?: Record<string, unknown>;
    }>("/settings")
      .then((settings) => {
        const values = settings.llm ?? {};
        setConfigs(values);
        setCache(settings.cache ?? {});
        const rest = { ...settings };
        delete rest.llm;
        delete rest.cache;
        setAdvanced(JSON.stringify(rest, null, 2));
        const first = Object.keys(values)[0] ?? "";
        setSelected(first);
        setHeaders(
          JSON.stringify(
            Object.hasOwn(values, first) ? values[first].extra_headers : {},
          ),
        );
      })
      .catch((reason: unknown) => {
        setMessage(String(reason));
      });
  }, []);
  const current = configs[selected] ?? emptyConfig;
  const update = (patch: Partial<LLMConfig>) => {
    if (!selected) return;
    setConfigs({ ...configs, [selected]: { ...current, ...patch } });
  };
  const save = async () => {
    try {
      const extra_headers = JSON.parse(headers) as Record<string, string>;
      const other = JSON.parse(advanced) as Record<string, unknown>;
      const result = await api<{ llm: Record<string, LLMConfig> }>(
        "/settings",
        {
          method: "PUT",
          body: JSON.stringify({
            ...other,
            llm: Object.fromEntries(
              Object.entries(configs).map(([name, config]) => [
                name,
                selected === name ? { ...config, extra_headers } : config,
              ]),
            ),
            cache,
          }),
        },
      );
      setConfigs(result.llm);
      setMessage("设置已保存");
    } catch (reason) {
      setMessage(String(reason));
    }
  };
  return (
    <div className="modal-backdrop" role="dialog" aria-label="设置">
      <section className="modal settings-modal">
        <header className="modal-header">
          <div>
            <span className="dialog-icon">
              <Icon name="settings" />
            </span>
            <div>
              <h2>设置</h2>
              <p>管理模型连接、运行保留策略与本地服务</p>
            </div>
          </div>
          <button className="icon-button" aria-label="关闭" onClick={onClose}>
            <Icon name="close" />
          </button>
        </header>
        <div className="settings-toolbar">
          <label className="inline-field">
            <span>LLM 配置</span>
            <select
              aria-label="配置名"
              value={selected}
              onChange={(event) => {
                setSelected(event.target.value);
                const config = configs[event.target.value];
                setHeaders(
                  JSON.stringify(
                    Object.hasOwn(configs, event.target.value)
                      ? config.extra_headers
                      : {},
                  ),
                );
              }}
            >
              {!selected && <option value="">无配置</option>}
              {Object.keys(configs).map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <button
            className="button secondary"
            onClick={() => {
              const suffix = (Object.keys(configs).length + 1).toString();
              const name = `llm-${suffix}`;
              setConfigs({ ...configs, [name]: { ...emptyConfig } });
              setSelected(name);
              setHeaders("{}");
            }}
          >
            <Icon name="plus" />
            新增配置
          </button>
          <button
            className="button ghost danger-text"
            disabled={!selected}
            onClick={() => {
              const next = Object.fromEntries(
                Object.entries(configs).filter(([name]) => name !== selected),
              );
              setConfigs(next);
              setSelected(Object.keys(next)[0] ?? "");
            }}
          >
            <Icon name="trash" />
            删除配置
          </button>
        </div>
        <div className="settings-body">
          <div className="security-inline">
            <Icon name="shield" />
            <span>
              密钥仅由沙箱外的 LLMProxy 读取，不会写入日志、轨迹或打包产物。
            </span>
          </div>
          <section className="settings-card">
            <div className="settings-card-heading">
              <div>
                <h3>模型连接</h3>
                <p>OpenAI 兼容端点，节点只引用配置名。</p>
              </div>
              <span className="tag neutral">{selected || "未选择"}</span>
            </div>
            <div className="settings-form-grid">
              <label className="form-field wide">
                <span>Base URL</span>
                <input
                  aria-label="Base URL"
                  placeholder="https://api.openai.com/v1"
                  value={current.base_url}
                  onChange={(event) => {
                    update({ base_url: event.target.value });
                  }}
                />
              </label>
              <label className="form-field">
                <span>API Key</span>
                <input
                  aria-label="API Key"
                  type="password"
                  value={current.api_key}
                  onChange={(event) => {
                    update({ api_key: event.target.value });
                  }}
                />
              </label>
              <label className="form-field">
                <span>模型</span>
                <input
                  aria-label="模型"
                  value={current.model}
                  onChange={(event) => {
                    update({ model: event.target.value });
                  }}
                />
              </label>
              <label className="form-field">
                <span>超时秒数</span>
                <input
                  aria-label="超时秒数"
                  type="number"
                  value={current.timeout}
                  onChange={(event) => {
                    update({ timeout: Number(event.target.value) });
                  }}
                />
              </label>
              <label className="form-field wide">
                <span>额外请求头（JSON）</span>
                <textarea
                  aria-label="额外请求头（JSON）"
                  value={headers}
                  onChange={(event) => {
                    setHeaders(event.target.value);
                  }}
                />
              </label>
            </div>
          </section>
          <section className="settings-card">
            <div className="settings-card-heading">
              <div>
                <h3>运行与运维</h3>
                <p>配置本地历史保留和高级服务参数。</p>
              </div>
            </div>
            <label className="form-field retention-field">
              <span>最近 Run 保留数</span>
              <input
                aria-label="最近 Run 保留数"
                type="number"
                min={0}
                value={Number(cache.run_retention ?? 50)}
                onChange={(event) => {
                  setCache({
                    ...cache,
                    run_retention: Number(event.target.value),
                  });
                }}
              />
            </label>
            <label className="form-field">
              <span>运行与运维配置（JSON）</span>
              <textarea
                className="advanced-config"
                aria-label="运行与运维配置（JSON）"
                value={advanced}
                onChange={(event) => {
                  setAdvanced(event.target.value);
                }}
              />
              <small>server.host / server.port 保存后需要重启服务。</small>
            </label>
          </section>
        </div>
        <footer className="modal-footer">
          <p role="status">{message}</p>
          <button
            className="button secondary"
            disabled={!selected}
            onClick={() => {
              void api<{ ok: boolean }>(`/settings/llm/${selected}/test`, {
                method: "POST",
              })
                .then(() => {
                  setMessage("连接成功");
                })
                .catch((reason: unknown) => {
                  setMessage(String(reason));
                });
            }}
          >
            <Icon name="trigger" />
            测试连接
          </button>
          <button className="button primary" onClick={() => void save()}>
            <Icon name="save" />
            保存设置
          </button>
        </footer>
      </section>
    </div>
  );
}
