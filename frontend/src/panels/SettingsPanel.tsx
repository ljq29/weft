import { useEffect, useState } from "react";
import { api } from "../api/client";

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
  useEffect(() => {
    void api<{ llm?: Record<string, LLMConfig> }>("/settings")
      .then((settings) => {
        const values = settings.llm ?? {};
        setConfigs(values);
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
      const result = await api<{ llm: Record<string, LLMConfig> }>(
        "/settings",
        {
          method: "PUT",
          body: JSON.stringify({
            llm: Object.fromEntries(
              Object.entries(configs).map(([name, config]) => [
                name,
                selected === name ? { ...config, extra_headers } : config,
              ]),
            ),
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
      <section className="port-view">
        <h2>LLM 配置</h2>
        <button onClick={onClose}>关闭</button>
        <button
          onClick={() => {
            const suffix = (Object.keys(configs).length + 1).toString();
            const name = `llm-${suffix}`;
            setConfigs({ ...configs, [name]: { ...emptyConfig } });
            setSelected(name);
            setHeaders("{}");
          }}
        >
          新增配置
        </button>
        <button
          disabled={!selected}
          onClick={() => {
            const next = Object.fromEntries(
              Object.entries(configs).filter(([name]) => name !== selected),
            );
            setConfigs(next);
            setSelected(Object.keys(next)[0] ?? "");
          }}
        >
          删除配置
        </button>
        <label>
          配置名
          <select
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
        <label>
          Base URL
          <input
            aria-label="Base URL"
            value={current.base_url}
            onChange={(event) => {
              update({ base_url: event.target.value });
            }}
          />
        </label>
        <label>
          API Key
          <input
            aria-label="API Key"
            type="password"
            value={current.api_key}
            onChange={(event) => {
              update({ api_key: event.target.value });
            }}
          />
        </label>
        <label>
          模型
          <input
            aria-label="模型"
            value={current.model}
            onChange={(event) => {
              update({ model: event.target.value });
            }}
          />
        </label>
        <label>
          超时秒数
          <input
            aria-label="超时秒数"
            type="number"
            value={current.timeout}
            onChange={(event) => {
              update({ timeout: Number(event.target.value) });
            }}
          />
        </label>
        <label>
          额外请求头（JSON）
          <textarea
            aria-label="额外请求头（JSON）"
            value={headers}
            onChange={(event) => {
              setHeaders(event.target.value);
            }}
          />
        </label>
        <button onClick={() => void save()}>保存设置</button>
        <button
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
          测试连接
        </button>
        <p role="status">{message}</p>
      </section>
    </div>
  );
}
