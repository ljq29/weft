import { useEffect, useState } from "react";
import { api, formatApiError } from "../api/client";
import { Icon } from "../components/Icon";

interface LLMConfig {
  base_url: string;
  api_key: string;
  model: string;
  timeout: number;
  extra_headers: Record<string, string>;
}

interface RuntimeSettings {
  server: {
    host: string;
    port: number;
    open_browser: boolean;
    global_token: string;
  };
  sandbox: {
    default: string;
    allow_none_sandbox: boolean;
    network: string;
    authorized_roots: string[];
    sandboxie: {
      start_exe: string;
      box_prefix: string;
    };
  };
  excel: {
    backend: string;
    call_timeout: number;
    restart_after_timeouts: number;
  };
  agent: {
    pi_path: string;
    confirm_timeout_s: number;
    trace_full_prompt: boolean;
    trace_retention_days: number;
  };
  trigger: {
    http_wait_timeout_s: number;
  };
  logging: {
    level: string;
    retention_days: number;
  };
  cache: {
    max_mb: number;
    run_retention: number;
    chat_retention_days: number;
    memory_retention_days: number;
  };
}

type Settings = RuntimeSettings & { llm: Record<string, LLMConfig> };
type RuntimeSection = keyof RuntimeSettings;

const DEFAULT_SETTINGS: Settings = {
  server: {
    host: "127.0.0.1",
    port: 7788,
    open_browser: true,
    global_token: "",
  },
  sandbox: {
    default: "sandboxie",
    allow_none_sandbox: false,
    network: "deny",
    authorized_roots: [],
    sandboxie: {
      start_exe: "C:\\Program Files\\Sandboxie-Plus\\Start.exe",
      box_prefix: "WeftBox",
    },
  },
  excel: { backend: "xlwings", call_timeout: 60, restart_after_timeouts: 3 },
  agent: {
    pi_path: "",
    confirm_timeout_s: 600,
    trace_full_prompt: false,
    trace_retention_days: 7,
  },
  trigger: { http_wait_timeout_s: 300 },
  logging: { level: "INFO", retention_days: 14 },
  cache: {
    max_mb: 2048,
    run_retention: 50,
    chat_retention_days: 30,
    memory_retention_days: 30,
  },
  llm: {},
};

const emptyConfig: LLMConfig = {
  base_url: "",
  api_key: "",
  model: "",
  timeout: 120,
  extra_headers: {},
};

const providers = [
  {
    id: "custom",
    label: "自定义",
    baseUrl: "",
    placeholder: "https://example.com/v1",
  },
  {
    id: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    placeholder: "",
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    placeholder: "",
  },
  {
    id: "siliconflow",
    label: "SiliconFlow",
    baseUrl: "https://api.siliconflow.cn/v1",
    placeholder: "",
  },
  {
    id: "ollama",
    label: "Ollama",
    baseUrl: "http://127.0.0.1:11434/v1",
    placeholder: "",
  },
  {
    id: "newapi",
    label: "NewAPI",
    baseUrl: "",
    placeholder: "https://your-newapi.example/v1",
  },
  {
    id: "axonhub",
    label: "AxonHub",
    baseUrl: "",
    placeholder: "https://your-axonhub.example/v1",
  },
] as const;

function normalizeSettings(value: Partial<Settings>): Settings {
  return {
    server: { ...DEFAULT_SETTINGS.server, ...(value.server ?? {}) },
    sandbox: {
      ...DEFAULT_SETTINGS.sandbox,
      ...(value.sandbox ?? {}),
      sandboxie: {
        ...DEFAULT_SETTINGS.sandbox.sandboxie,
        ...(value.sandbox?.sandboxie ?? {}),
      },
    },
    excel: { ...DEFAULT_SETTINGS.excel, ...(value.excel ?? {}) },
    agent: { ...DEFAULT_SETTINGS.agent, ...(value.agent ?? {}) },
    trigger: { ...DEFAULT_SETTINGS.trigger, ...(value.trigger ?? {}) },
    logging: { ...DEFAULT_SETTINGS.logging, ...(value.logging ?? {}) },
    cache: { ...DEFAULT_SETTINGS.cache, ...(value.cache ?? {}) },
    llm: value.llm ?? {},
  };
}

export function modelIdsFromResponse(models: unknown[]): string[] {
  return models.flatMap((model) => {
    if (typeof model !== "object" || model === null || !("id" in model))
      return [];
    const id = (model as { id?: unknown }).id;
    return typeof id === "string" && id ? [id] : [];
  });
}

function nextConnectionName(configs: Record<string, LLMConfig>): string {
  let index = Object.keys(configs).length + 1;
  while (Object.hasOwn(configs, `llm-${String(index)}`)) index += 1;
  return `llm-${String(index)}`;
}

function TextField({
  label,
  value,
  onChange,
  type = "text",
  placeholder = "",
  wide = false,
  disabled = false,
  readOnly = false,
  list,
}: {
  label: string;
  value: string;
  onChange?: (value: string) => void;
  type?: "text" | "password";
  placeholder?: string;
  wide?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  list?: string;
}) {
  return (
    <label className={`form-field${wide ? " wide" : ""}`}>
      <span>{label}</span>
      <input
        aria-label={label}
        type={type}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        readOnly={readOnly}
        list={list}
        onChange={(event) => onChange?.(event.target.value)}
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled = false,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <label className="form-field">
      <span>{label}</span>
      <input
        aria-label={label}
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => {
          onChange(Number(event.target.value));
        }}
      />
    </label>
  );
}

function ToggleField({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="form-field">
      <span>{label}</span>
      <input
        aria-label={label}
        type="checkbox"
        checked={value}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  options: readonly { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="form-field">
      <span>{label}</span>
      <select
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [selected, setSelected] = useState("");
  const [provider, setProvider] = useState("custom");
  const [models, setModels] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const configs = settings.llm;
  const current = configs[selected] ?? emptyConfig;
  const currentProvider =
    providers.find((item) => item.id === provider) ?? providers[0];

  useEffect(() => {
    void api<Partial<Settings>>("/settings")
      .then((stored) => {
        const values = normalizeSettings(stored);
        setSettings(values);
        const first = Object.keys(values.llm)[0] ?? "";
        setSelected(first);
        const baseUrl = first ? values.llm[first].base_url : "";
        setProvider(
          providers.find((item) => item.baseUrl && item.baseUrl === baseUrl)
            ?.id ?? "custom",
        );
      })
      .catch((reason: unknown) => {
        setMessage(formatApiError(reason));
      });
  }, []);

  const update = (patch: Partial<LLMConfig>) => {
    if (!selected) return;
    setSettings((previous) => ({
      ...previous,
      llm: {
        ...previous.llm,
        [selected]: { ...(previous.llm[selected] ?? emptyConfig), ...patch },
      },
    }));
  };

  const updateSection = <K extends RuntimeSection>(
    section: K,
    patch: Partial<Settings[K]>,
  ) => {
    setSettings((previous) => ({
      ...previous,
      [section]: { ...previous[section], ...patch },
    }));
  };

  const selectConnection = (name: string) => {
    setSelected(name);
    setModels([]);
    setMessage("");
    setProvider(
      providers.find(
        (item) => item.baseUrl && item.baseUrl === configs[name].base_url,
      )?.id ?? "custom",
    );
  };

  const addConnection = () => {
    const name = nextConnectionName(configs);
    setSettings((previous) => ({
      ...previous,
      llm: {
        ...previous.llm,
        [name]: { ...emptyConfig, extra_headers: {} },
      },
    }));
    setSelected(name);
    setProvider("custom");
    setModels([]);
    setMessage("");
  };

  const removeConnection = () => {
    const next = Object.fromEntries(
      Object.entries(configs).filter(([name]) => name !== selected),
    );
    setSettings({ ...settings, llm: next });
    setSelected(Object.keys(next)[0] ?? "");
    setModels([]);
    setMessage("");
  };

  const updateHeaderKey = (index: number, key: string) => {
    const entries = Object.entries(current.extra_headers);
    if (
      entries.some(
        ([existing], itemIndex) => itemIndex !== index && existing === key,
      )
    ) {
      setMessage("请求头名称不能重复");
      return;
    }
    const value = entries[index]?.[1] ?? "";
    entries[index] = [key, value];
    update({ extra_headers: Object.fromEntries(entries) });
  };

  const updateHeaderValue = (key: string, value: string) => {
    update({ extra_headers: { ...current.extra_headers, [key]: value } });
  };

  const addHeader = () => {
    let key = "X-Custom-Header";
    let index = 2;
    while (Object.hasOwn(current.extra_headers, key)) {
      key = `X-Custom-Header-${String(index)}`;
      index += 1;
    }
    update({ extra_headers: { ...current.extra_headers, [key]: "" } });
  };

  const removeHeader = (key: string) => {
    update({
      extra_headers: Object.fromEntries(
        Object.entries(current.extra_headers).filter(([name]) => name !== key),
      ),
    });
  };

  const runDraft = async (action: "test" | "models") => {
    if (!selected) return;
    setBusy(action);
    setMessage("");
    try {
      const result = await api<{ ok: boolean; models: unknown[] }>(
        `/settings/llm/draft/${action}`,
        {
          method: "POST",
          body: JSON.stringify({ name: selected, ...current }),
        },
      );
      if (action === "models") {
        const ids = modelIdsFromResponse(result.models);
        setModels(ids);
        setMessage(
          `已获取 ${String(ids.length)} 个模型，可从默认模型下拉列表选择`,
        );
      } else {
        setMessage("当前草稿连接成功，无需先保存");
      }
    } catch (reason) {
      setMessage(formatApiError(reason));
    } finally {
      setBusy("");
    }
  };

  const save = async () => {
    setBusy("save");
    setMessage("");
    try {
      const result = await api<Settings>("/settings", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
      setSettings(normalizeSettings(result));
      setMessage("设置已保存；server.host / server.port 变更需重启服务后生效");
    } catch (reason) {
      setMessage(formatApiError(reason));
    } finally {
      setBusy("");
    }
  };

  const authorizedRoots = settings.sandbox.authorized_roots;
  const disabled = !selected || busy !== "";

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
        <div className="settings-body">
          <div className="security-inline">
            <Icon name="shield" />
            <span>
              固定使用 OpenAI Chat Completions；密钥仅由沙箱外的 LLMProxy
              读取，不写入日志、轨迹或打包产物。
            </span>
          </div>
          <div className="settings-form-grid">
            <section className="settings-card">
              <div className="settings-card-heading">
                <div>
                  <h3>连接列表</h3>
                  <p>节点按连接名称引用，不包含渠道调度或多 Key 轮询。</p>
                </div>
              </div>
              <div className="run-list" aria-label="连接列表">
                {Object.entries(configs).map(([name, config]) => (
                  <button
                    key={name}
                    className={`run-item${selected === name ? " selected" : ""}`}
                    disabled={busy !== ""}
                    onClick={() => {
                      selectConnection(name);
                    }}
                  >
                    <Icon name="agent" />
                    <span>
                      <strong>{name}</strong>
                      <small>{config.base_url || "未填写 Base URL"}</small>
                    </span>
                  </button>
                ))}
                {Object.keys(configs).length === 0 && (
                  <p className="bottom-empty">暂无连接</p>
                )}
              </div>
              <button
                className="button secondary"
                disabled={busy !== ""}
                onClick={addConnection}
              >
                <Icon name="plus" />
                新增连接
              </button>
            </section>
            <section className="settings-card wide">
              <div className="settings-card-heading">
                <div>
                  <h3>当前命名连接</h3>
                  <p>预设仅填写 Base URL，不引入厂商 SDK。</p>
                </div>
                <button
                  className="button ghost danger-text"
                  disabled={disabled}
                  onClick={removeConnection}
                >
                  <Icon name="trash" />
                  删除连接
                </button>
              </div>
              <div className="settings-form-grid">
                <TextField
                  label="连接名称"
                  value={selected || "未选择"}
                  readOnly
                />
                <SelectField
                  label="服务商预设"
                  value={provider}
                  options={providers.map((item) => ({
                    value: item.id,
                    label: item.label,
                  }))}
                  disabled={disabled}
                  onChange={(value) => {
                    setProvider(value);
                    const preset = providers.find((item) => item.id === value);
                    if (preset?.baseUrl) {
                      update({ base_url: preset.baseUrl });
                      setModels([]);
                    }
                  }}
                />
                <SelectField
                  label="协议"
                  value="openai-chat-completions"
                  options={[
                    {
                      value: "openai-chat-completions",
                      label: "OpenAI Chat Completions",
                    },
                  ]}
                  disabled
                  onChange={() => undefined}
                />
                <TextField
                  label="Base URL"
                  value={current.base_url}
                  placeholder={
                    currentProvider.placeholder || "https://example.com/v1"
                  }
                  wide
                  disabled={disabled}
                  onChange={(value) => {
                    setProvider("custom");
                    setModels([]);
                    update({ base_url: value });
                  }}
                />
                <TextField
                  label="API Key"
                  type="password"
                  value={current.api_key}
                  disabled={disabled}
                  onChange={(value) => {
                    update({ api_key: value });
                  }}
                />
                <TextField
                  label="默认模型"
                  value={current.model}
                  list="llm-model-options"
                  disabled={disabled}
                  onChange={(value) => {
                    update({ model: value });
                  }}
                />
                <datalist id="llm-model-options">
                  {models.map((model) => (
                    <option key={model} value={model} />
                  ))}
                </datalist>
                <NumberField
                  label="超时秒数"
                  value={current.timeout}
                  min={0.001}
                  max={600}
                  step={0.001}
                  disabled={disabled}
                  onChange={(value) => {
                    update({ timeout: value });
                  }}
                />
              </div>
              <div className="table-actions">
                <button
                  className="button secondary"
                  disabled={disabled || !current.base_url}
                  onClick={() => void runDraft("models")}
                >
                  <Icon name="down" />
                  {busy === "models" ? "正在获取…" : "从当前草稿获取模型"}
                </button>
              </div>
              <div className="settings-card-heading">
                <div>
                  <h3>额外请求头</h3>
                  <p>按名称和值逐项编辑，保存为原有 extra_headers 对象。</p>
                </div>
                <button
                  className="button ghost"
                  disabled={disabled}
                  onClick={addHeader}
                >
                  <Icon name="plus" />
                  添加请求头
                </button>
              </div>
              {Object.entries(current.extra_headers).map(
                ([key, value], index) => (
                  <div className="settings-form-grid" key={index}>
                    <TextField
                      label={`请求头名称 ${String(index + 1)}`}
                      value={key}
                      disabled={disabled}
                      onChange={(value) => {
                        updateHeaderKey(index, value);
                      }}
                    />
                    <TextField
                      label={`请求头值 ${String(index + 1)}`}
                      value={value}
                      disabled={disabled}
                      onChange={(value) => {
                        updateHeaderValue(key, value);
                      }}
                    />
                    <button
                      className="button ghost danger-text"
                      aria-label={`删除请求头 ${String(index + 1)}`}
                      disabled={disabled}
                      onClick={() => {
                        removeHeader(key);
                      }}
                    >
                      <Icon name="trash" />
                    </button>
                  </div>
                ),
              )}
            </section>
          </div>

          <section className="settings-card">
            <div className="settings-card-heading">
              <div>
                <h3>本地服务</h3>
                <p>server.host / server.port 保存后需要重启服务。</p>
              </div>
            </div>
            <div className="settings-form-grid">
              <TextField
                label="监听地址 server.host"
                value={settings.server.host}
                wide
                onChange={(value) => {
                  updateSection("server", { host: value });
                }}
              />
              <NumberField
                label="监听端口 server.port"
                value={settings.server.port}
                min={1}
                max={65535}
                onChange={(value) => {
                  updateSection("server", { port: value });
                }}
              />
              <ToggleField
                label="启动后打开浏览器"
                value={settings.server.open_browser}
                onChange={(value) => {
                  updateSection("server", { open_browser: value });
                }}
              />
              <TextField
                label="非本机监听全局令牌"
                type="password"
                value={settings.server.global_token}
                wide
                onChange={(value) => {
                  updateSection("server", { global_token: value });
                }}
              />
            </div>
          </section>

          <section className="settings-card">
            <div className="settings-card-heading">
              <div>
                <h3>沙箱</h3>
                <p>配置默认隔离方式、网络策略与 Sandboxie 路径。</p>
              </div>
            </div>
            <div className="settings-form-grid">
              <SelectField
                label="默认沙箱"
                value={settings.sandbox.default}
                options={[
                  { value: "sandboxie", label: "sandboxie" },
                  { value: "none", label: "none" },
                ]}
                onChange={(value) => {
                  updateSection("sandbox", { default: value });
                }}
              />
              <SelectField
                label="沙箱网络"
                value={settings.sandbox.network}
                options={[
                  { value: "deny", label: "deny" },
                  { value: "allow", label: "allow" },
                ]}
                onChange={(value) => {
                  updateSection("sandbox", { network: value });
                }}
              />
              <ToggleField
                label="允许 NoneSandbox"
                value={settings.sandbox.allow_none_sandbox}
                onChange={(value) => {
                  updateSection("sandbox", { allow_none_sandbox: value });
                }}
              />
              <TextField
                label="Sandboxie Start.exe"
                value={settings.sandbox.sandboxie.start_exe}
                wide
                onChange={(value) => {
                  setSettings((previous) => ({
                    ...previous,
                    sandbox: {
                      ...previous.sandbox,
                      sandboxie: {
                        ...previous.sandbox.sandboxie,
                        start_exe: value,
                      },
                    },
                  }));
                }}
              />
              <TextField
                label="Sandboxie Box 前缀"
                value={settings.sandbox.sandboxie.box_prefix}
                onChange={(value) => {
                  setSettings((previous) => ({
                    ...previous,
                    sandbox: {
                      ...previous.sandbox,
                      sandboxie: {
                        ...previous.sandbox.sandboxie,
                        box_prefix: value,
                      },
                    },
                  }));
                }}
              />
            </div>
            <div className="settings-card-heading">
              <div>
                <h3>授权目录</h3>
                <p>逐行维护 sandbox.authorized_roots。</p>
              </div>
              <button
                className="button ghost"
                onClick={() => {
                  updateSection("sandbox", {
                    authorized_roots: [...authorizedRoots, ""],
                  });
                }}
              >
                <Icon name="plus" />
                添加目录
              </button>
            </div>
            {authorizedRoots.map((root, index) => (
              <div className="table-actions" key={index}>
                <TextField
                  label={`授权目录 ${String(index + 1)}`}
                  value={root}
                  wide
                  onChange={(value) => {
                    updateSection("sandbox", {
                      authorized_roots: authorizedRoots.map(
                        (item, itemIndex) =>
                          itemIndex === index ? value : item,
                      ),
                    });
                  }}
                />
                <button
                  className="button ghost danger-text"
                  aria-label={`删除授权目录 ${String(index + 1)}`}
                  onClick={() => {
                    updateSection("sandbox", {
                      authorized_roots: authorizedRoots.filter(
                        (_, itemIndex) => itemIndex !== index,
                      ),
                    });
                  }}
                >
                  <Icon name="trash" />
                </button>
              </div>
            ))}
          </section>

          <section className="settings-card">
            <div className="settings-card-heading">
              <div>
                <h3>Excel 与 Agent</h3>
                <p>配置外部进程、超时和轨迹保留。</p>
              </div>
            </div>
            <div className="settings-form-grid">
              <TextField
                label="Excel 后端"
                value={settings.excel.backend}
                onChange={(value) => {
                  updateSection("excel", { backend: value });
                }}
              />
              <NumberField
                label="Excel 调用超时秒数"
                value={settings.excel.call_timeout}
                min={0.001}
                max={600}
                step={0.001}
                onChange={(value) => {
                  updateSection("excel", { call_timeout: value });
                }}
              />
              <NumberField
                label="Excel 超时后重启阈值"
                value={settings.excel.restart_after_timeouts}
                min={1}
                max={100}
                onChange={(value) => {
                  updateSection("excel", { restart_after_timeouts: value });
                }}
              />
              <TextField
                label="pi 可执行文件路径"
                value={settings.agent.pi_path}
                wide
                onChange={(value) => {
                  updateSection("agent", { pi_path: value });
                }}
              />
              <NumberField
                label="Agent 审批超时秒数"
                value={settings.agent.confirm_timeout_s}
                min={0.001}
                max={86400}
                step={0.001}
                onChange={(value) => {
                  updateSection("agent", { confirm_timeout_s: value });
                }}
              />
              <ToggleField
                label="轨迹记录完整 Prompt"
                value={settings.agent.trace_full_prompt}
                onChange={(value) => {
                  updateSection("agent", { trace_full_prompt: value });
                }}
              />
              <NumberField
                label="Agent 轨迹保留天数"
                value={settings.agent.trace_retention_days}
                min={0}
                max={3650}
                onChange={(value) => {
                  updateSection("agent", { trace_retention_days: value });
                }}
              />
              <NumberField
                label="HTTP Trigger 等待秒数"
                value={settings.trigger.http_wait_timeout_s}
                min={0.001}
                max={3600}
                step={0.001}
                onChange={(value) => {
                  updateSection("trigger", { http_wait_timeout_s: value });
                }}
              />
            </div>
          </section>

          <section className="settings-card">
            <div className="settings-card-heading">
              <div>
                <h3>日志与缓存</h3>
                <p>配置日志级别、磁盘上限及各类历史保留策略。</p>
              </div>
            </div>
            <div className="settings-form-grid">
              <SelectField
                label="日志级别"
                value={settings.logging.level}
                options={["DEBUG", "INFO", "WARN", "ERROR"].map((level) => ({
                  value: level,
                  label: level,
                }))}
                onChange={(value) => {
                  updateSection("logging", { level: value });
                }}
              />
              <NumberField
                label="日志保留天数"
                value={settings.logging.retention_days}
                min={0}
                max={3650}
                onChange={(value) => {
                  updateSection("logging", { retention_days: value });
                }}
              />
              <NumberField
                label="缓存上限 MB"
                value={settings.cache.max_mb}
                min={1}
                max={1048576}
                onChange={(value) => {
                  updateSection("cache", { max_mb: value });
                }}
              />
              <NumberField
                label="最近 Run 保留数"
                value={settings.cache.run_retention}
                min={0}
                max={100000}
                onChange={(value) => {
                  updateSection("cache", { run_retention: value });
                }}
              />
              <NumberField
                label="对话保留天数"
                value={settings.cache.chat_retention_days}
                min={0}
                max={3650}
                onChange={(value) => {
                  updateSection("cache", { chat_retention_days: value });
                }}
              />
              <NumberField
                label="记忆保留天数"
                value={settings.cache.memory_retention_days}
                min={0}
                max={3650}
                onChange={(value) => {
                  updateSection("cache", { memory_retention_days: value });
                }}
              />
            </div>
          </section>
        </div>
        <footer className="modal-footer">
          <p role="status">{message}</p>
          <button
            className="button secondary"
            disabled={disabled || !current.base_url}
            onClick={() => void runDraft("test")}
          >
            <Icon name="trigger" />
            {busy === "test" ? "正在测试…" : "测试当前草稿"}
          </button>
          <button
            className="button primary"
            disabled={busy !== ""}
            onClick={() => void save()}
          >
            <Icon name="save" />
            {busy === "save" ? "正在保存…" : "保存设置"}
          </button>
        </footer>
      </section>
    </div>
  );
}
