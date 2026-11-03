# Weft 数据模型

|项|值|
| ------| -------------------------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`01-prd.md` §5 核心概念、`03-architecture.md`|
|下游|`05-api.md`、`09-nodes-v1.md`、实现代码（Pydantic 模型以本文为准）|

本文是**规范性**文档：字段名、类型、枚举值即实现要求。所有模型在代码中为 Pydantic v2 类，JSON Schema 由其导出。

---

## 1. 工作流目录

```
<name>.weft/
├── workflow.json          # 图定义（§2），唯一必需文件
├── pyproject.toml         # 依赖声明；[tool.weft] 段存元数据
├── uv.lock                # 锁定（uv 生成）
├── nodes/                 # 用户自定义节点（@weft.node）
├── prompts/               # prompt 文件（Prompt Template source: file）
├── data/                  # 约定的数据目录（非强制）
├── .gitignore             # 生成：.runs/ .venv/ __pycache__/
├── .venv/                 # uv 管理，不打包
└── .runs/                 # 运行产物，不打包
    ├── cache/<node_id>/{<port>.arrow|<port>.json, meta.json}  # 仅 pure 节点的可复用缓存
    ├── memory/<session_id>.jsonl # P1 Memory 节点数据
    ├── chat/<session_id>.jsonl   # UI 会话记录，不等于 Memory
    └── <run_id>/
        ├── workflow.json      # 入队时冻结的图、参数、变量与节点 manifest
        ├── meta.json          # Run 元数据（§6），含 workflow_revision 与端口 ValueRef
        ├── log.jsonl          # Run 日志
        ├── audit.jsonl        # 审计（§7）
        ├── changes.json       # 沙箱变更（§8）
        ├── ipc/               # Worker 间 Arrow 临时文件，不作历史输出真源
        ├── outputs/<node_id>/<port>  # 历史端口读取的不可变输出快照
        └── nodes/<node_id>.trace.jsonl
```

路径规则：`format: weft-path` 字段默认存相对 Root 的 POSIX 风格路径（`data/in.csv`）；绝对路径是用户显式声明的外部资源，允许使用但设计期与打包时警告。运行时由 `weft_ctx.resolve()` 统一解析；可信车道允许 Root 外操作，沙箱则另有目录授权。

## 2. workflow.json

```jsonc
{
  "schema_version": 1,
  "revision": 1,                        // 每次成功保存递增；PUT/PATCH 用作 CAS
  "id": "wf_8f3a...",              // 创建时生成；打包/导入保留，本机 duplicate 生成新 id
  "name": "weekly-report",
  "description": "",
  "created_at": "2025-01-01T00:00:00+08:00",
  "modified_at": "...",
  "settings": {
    "concurrency_policy": "queue",     // queue | drop | cancel_previous
    "sandbox": {
      "mode": "inherit",               // inherit | sandboxie | none
      "auto_apply_in_root": false
    }
  },
  "variables": [                        // 工作流级默认流变量（可被触发 overrides 覆盖）
    {"name": "target_wb", "type": "str", "value": "汇总.xlsx"}
  ],
  "nodes": [
    {
      "id": "n_0000a1b2",
      "type": "flow.trigger",
      "node_version": 1,
      "name": "Trigger",
      "position": {"x": 0, "y": 200},
      "params": {                       // 触发配置唯一真源，不另存顶层影子 trigger
        "manual": {"enabled": true},
        "chat": {"enabled": false},
        "schedule": {"enabled": false, "schedules": [{"cron": "0 9 * * 1-5"}]},
        "watch": {"enabled": false, "watches": [{"path": "data/inbox", "pattern": "*.xlsx",
                      "events": ["created"], "debounce_ms": 2000, "recursive": false}]},
        "http": {"enabled": false, "token_hash": "sha256:..."}
      },
      "disabled": false
    },
    {
      "id": "n_0000c3d4",              // "n_" + 8 hex
      "type": "table.row_filter",      // 命名空间.名称（§9）
      "node_version": 1,
      "name": "过滤低额",               // 用户可改显示名
      "position": {"x": 300, "y": 200},
      "comment": "",
      "params": {
        "column": "amount",
        "operator": ">",
        "value": {"$var": "threshold"} // 变量绑定（US-DES-06）
      },
      "disabled": false
    }
  ],
  "edges": [
    {"id": "e_c3d4", "source": "n_0000a1b2", "sourcePort": "variable",
     "target": "n_0000c3d4", "targetPort": "variables", "order": 0}
  ],
  "notes": [
    {"id": "note_1", "position": {...}, "size": {...}, "color": "#fff3c4", "markdown": "..."}
  ],
  "viewport": {"x": 0, "y": 0, "zoom": 1}
}
```

约束（保存时校验，违反为 ERROR 或 WARN）：

|规则|级别|
| ---------------------------------------------------------| --------------------|
|`nodes[].id` 唯一且匹配 `^n_[0-9a-f]{8}$`；`edges` 引用的节点与端口存在|ERROR|
|边两端端口类型兼容（§3.3）|ERROR|
|非 Tool/Variable 输入端口入边 ≤ 1；同一 Variable 输入端口的 `edges[].order` 为唯一整数|ERROR|
|动态输入通过实例化多个命名端口表达（如 Concatenate 的 `in_1...in_N`，N ≥ 2），每个命名端口仍最多一条入边；不允许单端口承载多条普通数据入边|ERROR|
|Merge 固定为两个命名输入端口，并声明 `accepts_partial_inputs=true`；仅命中一侧时可执行，两侧均 skipped 时 Merge 也 skipped|ERROR|
|折叠 Loop 后无环|ERROR|
|Loop Start/End 配对且嵌套合法|ERROR|
|恰好一个 `flow.trigger` 节点；触发配置只在该节点 params，不允许顶层影子 trigger|ERROR|
|`{"$var": name}` 引用的变量可能存在（静态可达性不保证，运行时兜底）|WARN|
|`format: weft-path` 字段为绝对路径|WARN（打包时汇总）|

## 3. 端口类型系统

### 3.1 六种类型

|类型|值（运行时）|缓存序列化|UI 颜色|语义|
| ------| ----------------------| ------------------------| ---------| ---------------------------------|
|`table`|`pyarrow.Table`|`.arrow`（Arrow IPC file）|蓝 `#3b82f6`|结构化表格|
|`excel`|描述符 dict（§3.2）|`.json`|橙 `#f97316`|Excel App/Workbook/Range 引用|
|`variable`|`dict[str, Any]`（一组流变量）|`.json`|红 `#ef4444`|标量参数集|
|`message`|`list[ChatMessage]`|`.json`|紫 `#a855f7`|LLM 消息序列|
|`tool`|`list[ToolDecl]`|不缓存（声明性）|绿 `#22c55e`|agent 工具|
|`flow`|无值（仅时序依赖）|不缓存|灰 `#9ca3af`|控制流（If/Try 分支、显式顺序）|

`ChatMessage = {role: system|user|assistant|tool, content: str, tool_calls?: [...], tool_call_id?: str, name?: str}`（OpenAI 规范子集）。

`ToolDecl = {name, description, parameters: JSONSchema, kind: node|sandboxed, requires_confirmation: bool, binding: {...}}`，`binding` 为实现侧路由信息（目标节点 ID 或沙箱工具名），不暴露给 LLM。

### 3.2 Excel 描述符

见 `03-architecture.md` §5.3。三种 `kind: app | workbook | range`，均可 JSON 序列化；`resolve()` 失败即缓存失效。

### 3.3 兼容矩阵

`is_compatible(src, dst)`：

|src \ dst|table|excel|variable|message|tool|flow|
| -----------| -------| -------| ----------| ---------| ------| ------|
|table|✓|—|—|—|—|✓*|
|excel|—|✓|—|—|—|✓*|
|variable|—|—|✓|—|—|✓*|
|message|—|—|—|✓|—|✓*|
|tool|—|—|—|—|✓|—|
|flow|—|—|—|—|—|✓|

✓* 任何数据端口可连到 `flow` 输入端口（只取时序，弃值）。除此之外无隐式转换；类型转换一律显式节点（`Table to Variables` 等）。此矩阵即 US-DES-03 AC-5 的测试表。

### 3.4 流变量作用域

- `variable` 端口的值是 dict，沿边流动时**合并**：多条 Variable 入边按显式 `edges[].order` 升序浅合并，高 order 覆盖低 order（UI 提示覆盖项）；同一输入端口的 order 必须唯一。
- 节点收到的变量作用域 = 工作流级 `variables` ⊕ 触发 `payload.overrides` ⊕ 所有到达本节点的 variable 端口值（就近优先）。
- `{"$var": name}` 在节点执行前由引擎解析；缺失则节点失败（US-DES-06 AC-4）。

## 4. ValueRef（IPC 与缓存的统一值引用）

```jsonc
{"kind": "table",    "path": ".runs/r_1/ipc/x/out.arrow", "hash": "sha256:...", "rows": 1000, "cols": 5}
{"kind": "json",     "inline": {...}, "hash": "sha256:..."}         // variable / message / excel 描述符
{"kind": "none"}                                                     // flow 端口
```

规则：`table` 永远走文件；JSON 值 ≤ 256 KB 时 `inline`，否则落文件给 `path`。`hash` 用于缓存键（`03-architecture.md` §2.4）。进入 Run 输出快照后，小 JSON 可以继续以 `inline` 不可变地存入 `meta.json`；带 `path` 的 ValueRef 必须指向 `.runs/<run_id>/outputs/` 而非临时 IPC。历史端口 API 从 `meta.json` 读取内联值，或从 outputs 读取文件值。

## 5. TriggerEvent

```jsonc
{
  "source": "manual | chat | schedule | file | http | excel",
  "ts": "ISO8601",
  "session_id": "s_...",            // chat 必有，其余可空
  "payload": {
    // manual:   {"overrides": {k: v}}
    // chat:     {"message": str, "history_len": int}
    // schedule: {"schedule_id": str, "scheduled_at": ISO8601}
    // file:     {"events": [{"path": str, "kind": "created|modified|deleted", "ts": ISO8601}]}
    // http:     {"body": any, "headers_subset": {...}}
    // excel:    {"workbook": str, "sheet": str, "address": str}（仅预留，v1 不接受运行）
  }
}
```

Trigger 节点 `variable` 端口输出 `{source, ts, session_id?, payload}`，不 flatten；聊天文本通过 `payload.message` 访问。`message` 端口 = chat 时 `[{role: "user", content: payload.message}]` 否则 `[]`；`table` 端口 = file 时 events 表（列 `path, kind, ts`）否则空表。TriggerManager 加载时从 Trigger 节点 params 派生运行视图，workflow 顶层不保存影子 trigger。

## 6. Run 与节点执行记录

```jsonc
// .runs/<run_id>/meta.json
{
  "run_id": "r_20250101_093000_a1b2",
  "workflow_id": "wf_8f3a...",
  "workflow_revision": 1,
  "frozen_workflow": ".runs/r_20250101_093000_a1b2/workflow.json",
  "trigger": { TriggerEvent },
  "scope": {"kind": "all | to_node | from_node | single", "node_id": null},
  "status": "queued | running | waiting | succeeded | failed | cancelled",
  "started_at": "...", "finished_at": "...",
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "llm_calls": 0, "tool_calls": 0},
  "nodes": {
    "n_0000a1b2": {
      "status": "executed | failed | ...", "started_at": "...", "finished_at": "...",
      "from_cache": false, "error": {"type": "...", "message": "...", "traceback": "..."},
      "outputs": {
        "out": {"kind": "table", "path": ".runs/r_20250101_093000_a1b2/outputs/n_0000a1b2/out.arrow", "hash": "sha256:..."},
        "variables": {"kind": "json", "inline": {"row_count": 1000}, "hash": "sha256:..."}
      }
    }
  }
}
```

`run_id` 格式：`r_<yyyymmdd>_<hhmmss>_<4hex>`，可排序。`workflow_revision` 与冻结文件共同确定本 Run 输入；历史端口读取 `outputs` 中的内联值或文件引用，默认保留最近 50 次 Run。节点状态与错误只存于 `meta.json`，Run 日志只存于 `log.jsonl`，agent 轨迹存于 `nodes/<node_id>.trace.jsonl`，不另存 `nodes/<node_id>.json`。

## 7. 审计记录（audit.jsonl，每行一条）

```jsonc
{"ts": "...", "run_id": "...", "node_id": "n_0000a1b2", "agent_kind": "agent_loop | pi",
 "lane": "trusted | sandboxed", "tool": "excel_read_range",
 "args_redacted": {...}, "status": "ok | error | rejected",
 "duration_ms": 123, "result_hash": "sha256:..."}
```

打码规则：键名匹配 `/key|token|password|secret/i` 的字符串值替换为 `"***"`；`Authorization` 等认证头、URL userinfo 与敏感 query 参数同样打码。完整 prompt 默认不写 trace，只有显式开启时才记录并按所设保留期限删除；原始 API key 不进入沙箱环境变量、stdout 或任何 trace。

## 8. 变更记录（changes.json）

```jsonc
{
  "run_id": "...", "collected_at": "...",
  "sandbox": "sandboxie | none",
  "audit_complete": true,
  "audit_warnings": [],
  "changes": [
    {"path": "D:/flows/demo.weft/out/a.txt",       // 真实目标路径（绝对）
     "rel_root": "out/a.txt",                       // Root 内时给出相对路径，否则 null
     "kind": "created | modified | deleted | renamed",
     "old_path": null, "new_path": null,           // renamed 时填写；其余为 null
     "baseline_hash": "sha256:... | null",
     "size": 1024, "is_text": true, "protected": false,
     "state": "pending | applied | conflict | failed | discarded",
     "error": null}
  ]
}
```

重命名优先由删除与创建的内容哈希匹配；无法可靠判断时保留删除+创建两条并写 `audit_warnings`。apply 前重算真实目标哈希，与基线不一致即 conflict；只有显式覆盖确认才能继续。

## 9. 节点类型命名空间

`<namespace>.<name>`，v1 命名空间：`flow` `table` `excel` `file` `agent` `code`。用户节点强制 `user.<name>`。代码中的节点声明/JSON Schema 是参数真源；`09-nodes-v1.md` 由导出器生成，是只读参考。用户故事仍是行为与 AC 真源。

## 10. 用户级配置（config.toml）

```toml
[server]
host = "127.0.0.1"
port = 7788
open_browser = true
global_token = ""            # 监听非本机时必填

[llm.default]
base_url = "https://api.example.com/v1"
api_key  = "sk-..."          # 仅主机 LLMProxy 读取，不下发沙箱
model    = "gpt-4o"
timeout  = 120

[excel]
backend = "xlwings"          # xlwings | fake
call_timeout = 60

[sandbox]
default = "sandboxie"        # sandboxie | none；none 仅用于影子目录审批流模拟
allow_none_sandbox = false   # 显式允许 none；不允许任意 bash/pi 在 none 下执行
network = "deny"             # deny | allowlist；默认仅放行指定环回 LLMProxy
audit_roots = []             # Root 之外的显式授权目录

[sandbox.sandboxie]
start_exe = 'C:\Program Files\Sandboxie-Plus\Start.exe'
box_prefix = "WeftBox"        # 实际每 Run 为 WeftBox-<run_id>

[agent]
pi_path = ""                 # 空 = PATH 查找
confirm_timeout_s = 600
trace_full_prompt = false
trace_retention_days = 7

[trigger]
http_wait_timeout_s = 300

[logging]
level = "INFO"
retention_days = 14

[cache]
max_mb = 2048
run_retention = 50
chat_retention_days = 30     # 0 = 不自动清理
memory_retention_days = 30   # 0 = 不自动清理
```

## 11. 版本与迁移

- `schema_version` 整数递增；迁移函数 `migrate_v{n}_to_v{n+1}(doc) -> doc` 注册于 `weft.workflow.migrations`，逐级执行，迁移前备份 `workflow.json.bak.v{n}`。
- 节点级：`node_version` 不匹配时调用节点类的 `migrate_params(old_version, params) -> params`；未实现则原样保留并 WARN。
- 未知节点类型：加载为 `flow.placeholder`（保留原 type/params，不可执行），保存时原样写回，不丢数据（US-PKG-05 AC-3）。
