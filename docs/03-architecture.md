# 03-architecture.md

**Weft 架构设计文档**

|项|值|
| ------| -----------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`01-prd.md`（§9 约束、§10 决策）、`02-user-stories.md`|
|下游|`04-data-model.md`、`05-api.md`、`06-engineering.md`|

本文回答"系统怎么拆、进程怎么分、数据怎么流、为什么这样"。与 PRD 决策记录（D-01..D-13）重复的理由不再展开，只引用编号。

---

## 1. 总览

### 1.1 进程拓扑

```
┌─────────────────────────── 用户机器（Windows，登录会话） ───────────────────────────┐
│  浏览器 (React + React Flow) ── HTTP / WebSocket (127.0.0.1:7788)                  │
│                                      ▼                                             │
│  ┌──────────────────── weft 服务进程（Weft 自带环境） ────────────────────┐          │
│  │ FastAPI / WorkflowStore / Engine / TriggerManager                     │          │
│  │ ExcelWorker（全局 STA 串行） / SandboxManager / AgentRuntime           │◄─┐ COM    │
│  │ LLMProxy（主机读取原始 key；只允许配置的 LLM 端点）                     │  │       │
│  └───────┬──────────────────────────────┬───────────────────────────────┘  │       │
│          │ JSON-RPC stdio + Arrow IPC   │ Start.exe /box:WeftBox-<run_id> │        │
│          ▼                              ▼                                 │        │
│  ┌──────────────────┐          ┌───────────────────────┐          ┌─────────┴─────┐ │
│  │ Worker pool / Run │          │ Sandboxie / 独立 box  │          │ Excel.exe     │ │
│  │ 默认 4，结束全退出 │          │ tools / pi            │          │ 可见或隐藏    │ │
│  │ (<root>/.venv)    │          │ 网络默认拒绝          │          └───────────────┘ │
│  └──────────────────┘          └──────────┬────────────┘                            │
└───────────────────────────────────────────┼─────────────────────────────────────────┘
        沙箱仅访问本地代理地址 + 配置名        │ HTTPS（由主机 LLMProxy 签发）
                                             ▼
                                  OpenAI 兼容网关（NewAPI 等）
```

要点：

- **三类子进程**：Workflow Worker（可信车道的节点执行）、沙箱内进程（非可信车道）、Excel（被驱动的外部程序）。
- **ExcelWorker 在服务进程内**而不在 Workflow Worker 内——理由见 §5.2。
- 服务进程必须以登录用户普通进程运行（PRD §9.1），不能是 Windows 服务。

### 1.2 代码分层（服务进程内）

```
weft/
├── api/            # FastAPI 路由、WS、DTO —— 只做协议转换，不含业务
├── engine/         # 调度器、Run 状态机、冻结快照、缓存、循环/分支；暴露执行接口
├── nodes/          # 服务侧节点注册与服务 lane 实现；声明/JSON Schema 为参数真源
├── excel/          # ExcelBackend 接口、XlwingsBackend、FakeBackend、ExcelWorker
├── agent/          # LLMProxy/Client、Agent Loop、工具协议、审计
├── sandbox/        # Sandbox 接口、NoneSandbox、SandboxieSandbox、变更收集
├── triggers/       # TriggerManager 与 5 种触发源；从 Trigger params 派生运行视图
├── workflow/       # workflow.json 模型、校验、revision/CAS、迁移、打包
└── cli/            # weft serve/run/pack/unpack/doctor

packages/weft-worker/  # 独立包：Worker 入口、RPC、可信 Worker 内置节点实现
packages/weft-sdk/     # weft_ctx 与声明协议，不依赖主包/Worker
```

Engine 只暴露执行接口，trigger/agent 在上层调用，组合根负责注入；Engine 不 import 具体 triggers/agent。`api → application services → engine → {node contracts, workflow}`，excel/sandbox 等以接口注入；`weft-worker` 与主服务同版本并依赖 `weft-sdk`，禁止主机 `PYTHONPATH` 隐式复用。

---

## 2. 执行引擎

这是整个项目的核心资产（D-02）。

### 2.1 图模型

- 图 = 节点 + 有向边；边连接 `(node, output_port) → (node, input_port)`。
- 顶层图必须是 **DAG**，唯一例外是 `Loop Start → ... → Loop End` 区域：引擎在加载时识别成对的 Loop 节点，把中间子图折叠为一个"虚拟循环节点"后再做拓扑排序。折叠后仍非 DAG 则拒绝运行。
- Metanode 在加载时**内联展开**（节点 ID 加前缀 `meta_<id>/`），引擎不感知 Metanode，只有画布感知。
- 端口类型见 `04-data-model.md` §3；引擎只关心类型兼容与"值如何序列化到缓存"，不关心值的语义。
- 每个节点声明 `execution_lane`：`trusted_worker`（默认，在 Workflow Worker 执行）、`trusted_service`（在服务进程执行，用于 Excel、Agent、触发器等需要访问服务内单例的节点）、`sandboxed`（节点本身不执行，只是向 agent 提供沙箱工具）。

### 2.2 Run 状态机

```
                ┌──────────┐
   trigger ───► │  queued  │
                └────┬─────┘
                     │ 调度器取出（同工作流无活跃 Run）
                     ▼
                ┌──────────┐   confirm_request   ┌──────────┐
                │ running  │ ───────────────────► │ waiting  │
                │          │ ◄─────────────────── │          │
                └─┬──┬──┬──┘   confirm / timeout  └──────────┘
                  │  │  │
        全部完成   │  │  │ 任一节点失败且无 Try 捕获
                  │  │  └──────────► failed
                  │  │ cancel
                  │  └─────────────► cancelled
                  ▼
              succeeded
                  │
                  ▼ （所有终态）
          post_run: collect_changes → changes.json → 清理沙箱进程 → 关闭隐藏 Excel
```

节点状态机（与 UI 状态灯对应）：

```
unconfigured ──配置完整──► configured ──调度──► running ──► executed
                                 ▲                 │  ├──► failed
                                 │                 │  └──► cancelled
                                 │                 └──(分支未命中)──► skipped
                                 └──── 参数/上游变化、重置 ─────────────┘
```

### 2.3 调度算法

```python
async def run(graph, scope: ExecScope):
    order = topo_sort(graph.collapsed())          # Loop 区域已折叠
    ready = {n for n in order if indeg(n) == 0}
    inflight = set()
    while ready or inflight:
        for n in list(ready):
            ready.remove(n)                        # 每个节点最多出队一次
            if n not in scope:
                mark(n, skipped_by_scope)
                release_downstream(n, skipped=True) # 跳过同样递减下游 indeg 并传播
                continue
            if cache_hit(n):
                mark(n, executed_from_cache)
                release_downstream(n)
                continue
            inflight.add(spawn(execute(n)))
        if not inflight:
            continue
        done = await wait_any(inflight)
        inflight -= done
        for n in done:
            if n.failed and not inside_try(n):
                cancel_all()
                return FAILED
            release_downstream(n)                  # 分支节点只释放命中的下游
    assert all_nodes_terminal(graph)
```

- **ExecScope**：由"整体运行 / 执行到此 / 从此开始 / 仅本节点"计算出的节点集合（`02-user-stories.md` US-EXE-02/03）。
- **并行度**：`trusted_worker` 节点默认并行上限 4（可配）；`trusted_service` 中 Excel 节点由 ExcelWorker 天然串行；Agent 节点并行上限 2（LLM 限速考虑）。
- **分支**：`If/Switch` 执行后向引擎返回 `activated_ports`；未激活端口的下游整条链标记 `skipped`，`Merge` 类节点声明 `accepts_partial_inputs=True` 才能在部分输入 skipped 时执行。
- **循环**：虚拟循环节点内部是一个递归的 `run(subgraph, scope=all)`，每次迭代使用独立的 `IterationContext(index, total)`，缓存键混入迭代号（US-EXE-10 AC-4）。循环体内禁止再出现 Trigger。

### 2.4 冻结快照、缓存与 Run 输出

**冻结快照**：Run 入队时复制当前 `workflow.json`、解析后的工作流变量及节点 manifest 到 `.runs/<run_id>/workflow.json`，并记录 `workflow_revision`。该 Run 始终读取此快照；活跃 Run 中结构修改仍拒绝，允许的位置、注释等非结构修改只影响下一 Run。保存采用 revision/CAS，防止多个标签页覆盖。

|项|规则|
| ----------| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|执行策略|节点声明 `cache_policy: pure | volatile | side_effect`，缺省为 `side_effect`。副作用节点每次执行；LLM、实时 Excel Read 等 `volatile` 节点每次执行且禁止跨 Run 复用；只有显式声明的纯计算可复用输出|
|键|`sha256(node_type ‖ node_version ‖ implementation_hash ‖ canonical_json(resolved_params) ‖ sorted(port_name, content_hash) ‖ sorted(external_input_name, content_hash) ‖ user_code_hash ‖ uv_lock_hash ‖ iteration_index)`；`resolved_params` 是流变量注入后的参数|
|输入哈希|Table：Arrow IPC 文件 SHA-256；Variable/Message：canonical JSON 哈希；Excel 描述符：描述符 JSON 哈希。节点用 `cache_inputs` 显式声明引用外部状态的参数：`file` 对内容做 SHA-256，不用 mtime/size 代替；`directory` 按该节点相同的 path/pattern/recursive 规则枚举，对排序后的 `{path,name,size,modified,is_dir}` canonical JSON 做 SHA-256。未声明的参数只哈希字面值，不被隐式当作文件|
|缓存位置|`<root>/.runs/cache/<node_id>/<port>.{arrow,json}` + `<node_id>/meta.json`（含键、版本、写入时间）|
|Run 输出|`meta.json` 记录各节点 `outputs: {port: ValueRef}`；小 JSON 可不可变地内联，Table 与大 JSON 写入 `.runs/<run_id>/outputs/<node_id>/<port>`；历史端口 API 只读该快照，不读临时 IPC 或当前全局缓存|
|失效|键不匹配、meta 缺失或损坏、用户重置；Excel App/Workbook 描述符仅在 `resolve()` 成功后复用，失败时重跑对应连接节点；这不代表复用 Excel Read 的表格内容|
|清理|"重置全部"清空全局纯缓存；Run 输出默认随最近 50 次 Run 保留；缓存超过 `cache_max_mb`（默认 2 GB）按 LRU 删除；`.runs/chat/` 与 `.runs/memory/` 默认按 30 天清理，0 表示不自动清理|

### 2.5 取消

- Run 级 `asyncio.CancelledError` 传播到所有 inflight 节点。
- `trusted_worker` 节点：向拥有该任务的 Worker 发送 `cancel(node_exec_id)` RPC；用户代码通过 `weft_ctx.check_cancelled()` 协作取消；3 s 后未响应则 `CTRL_BREAK_EVENT`，再 3 s 后 kill。Run 终止时关闭整个 pool，其他 Run 不受影响。
- Agent 节点：取消 HTTP 流；当前轮返回后不再发起。
- Excel 节点：COM 调用无法中断，超时只放弃本次结果；ExcelWorker 仍被旧调用占用，后续 Excel 操作继续排队，UI 显示繁忙。
- 沙箱进程：只终止本 Run 独立 box 及其拥有的进程树，不发送全局 box 终止命令。

---

## 3. Workflow Worker 与 IPC

### 3.1 进程与依赖边界

- 用户依赖在 `<root>/.venv`，与 Weft 本体环境隔离（D-09，US-EXE-14）。
- 用户代码崩溃或死循环不拖垮服务；不同 Run 不复用 Python 全局状态。
- 每 Run 懒启动一个 Worker pool，默认并行度 4；单个 Worker 同时只处理一个 `execute`，pool 内多个真实子进程提供并行。Run 结束（含取消、崩溃）全部退出，不空闲保活。
- 主服务与 `weft-worker` 必须精确同版本，v1 不使用 `~=` 或隐式兼容范围。工作流标准 `dependencies` 由创建器写入 `weft-worker==<service_version>` 与用户依赖，`uv.lock` 同时锁定两者；服务升级后须由用户显式确认更新依赖、重锁并同步，未完成前拒绝运行；`[tool.weft]` 只存 Weft 元数据，uv 不会自动合并自定义依赖段。
- Worker 直接启动工作流 venv 中安装的 `weft-worker` 入口，禁止通过主机 `PYTHONPATH` 隐式复用代码。`weft-worker` 依赖 `weft-sdk`，包含 Worker 入口、RPC 和可信 Worker 内置节点实现；Excel COM 的 xlwings/pywin32 仍只在服务进程。
- 为 v2 Runner 预留：Runner 是远端 Worker pool，协议不变。

### 3.2 协议

**传输**：子进程 stdio，每行一个 JSON（JSON-RPC 2.0 子集）；stderr 作为日志通道，不用 socket。

**大数据不走 stdio**：Table 值以 Arrow IPC 文件传递，RPC 中只传路径。文件位于 `<root>/.runs/<run_id>/ipc/<node_exec_id>/<port>.arrow`，Worker 端用 `pa.memory_map` 映射读取；节点输出写文件后返回路径，引擎按需要提升为 Run 输出或纯缓存。这里只承诺减少复制，不宣称序列化、写盘、哈希和 DataFrame 转换全链路零拷贝。

**方法**：

|方向|方法|说明|
| ------| ------| -----------------------------------------|
|S→W|`init(root, run_id, node_types_manifest)`|启动后握手，Worker 加载冻结 manifest 与用户节点|
|S→W|`execute(node_exec_id, node_type, params, inputs: {port: ValueRef}, ctx)`|返回 `{outputs: {port: ValueRef}, activated_ports?}`；一个 Worker 一次仅一个请求|
|S→W|`cancel(node_exec_id)`||
|S→W|`shutdown()`||
|W→S|`log(node_exec_id, level, message)`|通知（无需响应）|
|W→S|`progress(node_exec_id, fraction, message?)`|通知|
|W→S|`tool_call(node_exec_id, tool, args)`|**预留**：v1 不用（Agent 在服务进程）|

`ValueRef` 定义见 `04-data-model.md` §4。`node_exec_id` 同时路由日志、取消与结果，pool scheduler 不为同一 Worker 并发派发第二个 execute。

### 3.3 Worker 侧 SDK（`weft_ctx`）

用户 Python 节点与自定义节点可用的最小 API：

```python
weft_ctx.root: Path                 # 工作流 Root 绝对路径
weft_ctx.run_id: str
weft_ctx.vars: dict                 # 冻结 Run 的流变量（只读视图）
weft_ctx.log(msg, level="INFO")
weft_ctx.progress(fraction, msg=None)
weft_ctx.check_cancelled()          # 抛 weft_ctx.Cancelled
weft_ctx.resolve(path) -> Path      # 默认相对 Root；绝对路径是显式外部资源
```

`weft_ctx` 由 `weft-sdk` 提供（纯 Python，无重依赖）。用户代码与相关依赖摘要进入缓存键，运行中发生的代码修改只影响下一 Run。

---

## 4. 节点系统

### 4.1 节点定义协议

每个节点类型是一个 Python 类，**声明**与**实现**分离：

```python
class RowFilter(Node):
    type = "table.row_filter"
    version = 1
    category = "table"
    lane = Lane.TRUSTED_WORKER
    cache_policy = CachePolicy.PURE   # 缺省 SIDE_EFFECT；volatile 禁止跨 Run 复用
    tool_capability = ToolCapability.READ_ONLY  # 默认不开放；另见 §4.3
    inputs = [Port("in", PortType.TABLE)]
    outputs = [Port("out", PortType.TABLE)]
    params_schema = {...}            # JSON Schema draft 2020-12，参数真源
    tool_exposed_params = []         # 允许经 NodeTool 暴露的参数白名单
    portable_params = ["path"]       # 标记 format: weft-path 的字段（打包检查）
    external_resources = []          # 运行前预检（US-PKG-07）
    cache_inputs = []                # ExternalInput(name, kind=file|directory)，纳入内容哈希

    def execute(self, ctx: NodeContext, inputs: dict, params: dict) -> dict:
        ...
```

- **动态输入**：节点可声明 `DynamicPortGroup(prefix="in_", port_type=PortType.TABLE, min_ports=2)`；保存时实例化为 `in_1...in_N` 命名端口，每个端口遵守单入边规则。Concatenate 使用该声明；Merge 使用两个固定命名输入和 `accepts_partial_inputs=True`。不引入普通数据端口的多入边模式。
- **声明部分**（type、version、ports、schema、cache_inputs）在服务进程与 Worker 两侧都可加载，用于 UI 表单生成、校验、缓存键；**实现部分**只在声明的 lane 对应的进程中加载。
- 注册表：内置节点通过包内扫描；用户节点通过 `<root>/nodes/*.py` 中的 `@weft.node` 装饰器注册，仅对该工作流可见。
- 节点 `execute` 对 Table 端口接收/返回 `polars.DataFrame`，框架负责 Arrow 转换（US-TBL-01 AC-1）。
- 节点通过 `ctx` 访问日志、进度、取消、Root、以及（仅 `trusted_service` lane）`ctx.excel`、`ctx.llm`、`ctx.sandbox` 服务句柄。

### 4.2 节点分类与 lane

|分类|lane|原因|
| -----------------------------------------------------------------------| ------------------------| ----------------------------------------------|
|表格、文件、Python Script、Shell|`trusted_worker`|需要用户依赖；可能很重|
|Excel|`trusted_service`|必须经 ExcelWorker（§5）|
|Agent（LLM Call、Agent Loop、Pi、Node as Tool、Prompt、Memory、Chat）|`trusted_service`|需要 LLM 客户端、审计、WS 流式推送、工具分发|
|Sandboxed Tools|`sandboxed`（声明性，不执行）|提供工具给 Agent|
|流程（Trigger、If、Switch、Loop、Try Start、Try End、Variable、Merge、Wait、HTTP Response）|`trusted_service`|引擎语义节点，轻量|

`trusted_service` 节点若需要 Table 输入，服务进程读取 Arrow 文件（服务本体环境自带 pyarrow/polars）。

### 4.3 Node as Tool 的执行路径

```
Agent Loop (service) ─tool_call─► ToolDispatcher ─► NodeTool.invoke(args)
     │                                                   │
     │                         校验 tool_capability + tool_exposed_params + 确认策略
     │                         params = 当前 Run 冻结节点参数 ⊕ 允许暴露的 args
     │                         inputs = 当前 Run 已物化的上游输入快照
     │                                                   ▼
     │                                   engine.execute_single(node, params, inputs, ephemeral=True)
     │                                                   │（按节点 lane 路由到 Worker 或 service）
     ◄──────────────── result_format 转字符串 ◄──────────┘
                       + 打码后的审计日志
```

`ephemeral=True` 表示不写全局缓存、不改变画布状态，但不绕过调度与资源约束。`execute_single` 进入同一 Run 的调度器：Worker 节点占用本 Run pool 的一个槽位，单个 Worker 仍只处理一个 execute；service 节点占用对应 lane 的并发额度。调用继承 Run 取消上下文与 `tool_timeout`，取消会取消正在执行或排队的工具调用；池满时排队而非另开绕过上限的进程。Agent 节点不可作为 NodeTool 目标，因此不允许递归 Agent/嵌套工具执行。

节点默认不开放工具能力；只读/纯计算节点可显式开放，Python/Shell/任意代码执行节点永不开放。写文件、Excel 写等副作用能力需设计者与调用时双重授权，默认逐次确认。

---

## 5. Excel 子系统

### 5.1 接口

```python
class ExcelBackend(Protocol):
    def connect(self, mode: Literal["attach_visible", "new_visible", "new_hidden"]) -> AppRef
    def workbook(self, app: AppRef, mode, name_or_path) -> WorkbookRef
    def sheet_names(self, wb: WorkbookRef) -> list[SheetInfo]
    def read_range(self, wb, sheet, range_spec, header, dtype_hints) -> pa.Table
    def write_table(self, wb, sheet, start, table, mode, options) -> RangeRef
    def update_cells(self, wb, sheet, cells: list[CellUpdate], allow_formula) -> None
    def manage_sheet(self, wb, action, name, new_name=None) -> None
    def save(self, wb, mode, path=None, fmt=None, overwrite=False) -> Path | None
    def run_macro(self, wb, macro, args) -> Any
    def fast_mode(self, app) -> ContextManager        # ScreenUpdating/Calculation/Events
    def close_app(self, app, on_finish) -> None
    def resolve(self, ref: AppRef | WorkbookRef) -> bool  # 缓存命中时重新解析
```

实现：`XlwingsBackend`（v1）、`FakeExcelBackend`（内存实现，CI 用）。xlOil 后端 v2 考虑。

### 5.2 ExcelWorker

- 服务进程内的**单例线程**，线程启动时 `pythoncom.CoInitialize()`（STA）。
- 所有 `ExcelBackend` 调用通过 `await worker.submit(fn, *args)`，内部为 `queue.Queue` + `concurrent.futures.Future`。
- 放在服务进程而非 Workflow Worker 的原因：

  1. 用户可见 Excel 实例是**全局资源**，多工作流共享一条串行队列（US-EXE-13 AC-3）。
  2. Workflow Worker pool 随 Run 结束全部退出，COM 连接若放其中会使隐藏实例生命周期失控。
  3. 经授权的 NodeTool 调 Excel 节点时与 Agent 同在服务进程，路径最短。
- 代价：只有服务进程环境安装 `xlwings` + `pywin32`，Workflow Worker 不重复安装；非 Windows 可用 Fake 做契约测试，但不得据此宣称真机验证。
- 实例与引用：`RefRegistry` 维护描述符→COM 对象及 owned PID/进程创建时间/Run/心跳；多实例让用户按 PID/窗口/工作簿选择并持久化目标，不猜测最近活动实例。无人值守 Run 必须唯一解析该目标；PID 变化时可按已选工作簿重新解析，无法解析或匹配多个实例时运行失败，不自动改连其他实例，也不默认回退隐藏实例。Run 结束释放引用，attach 可见实例不关闭；new_hidden 必须由用户显式选择 save/discard，报告未保存工作簿。
- fast_mode：可见实例默认 false，隐藏实例默认 true；结束时恢复 ScreenUpdating、Calculation、EnableEvents。
- 超时：`submit` 带 timeout；超时后本次请求失败/结果被丢弃，但 ExcelWorker 仍被旧 COM 调用占用，后续任务继续排队且 UI 显示繁忙，不宣称立即可用。
- 错误映射：`pywintypes.com_error` 的 HRESULT → 可读错误（`0x800AC472` 等 → "Excel is busy"），见 US-XLS-12。

### 5.3 描述符

```json
{"kind": "app", "pid": 1234, "visible": true, "owned": false}
{"kind": "workbook", "app_pid": 1234, "name": "ref.xlsx", "path": "D:/.../ref.xlsx", "saved": true}
{"kind": "range", "workbook": {...}, "sheet": "Sheet1", "address": "A1:E101", "rows": 101, "cols": 5}
```

`owned: true` 表示由 Weft 启动（Run 结束可关闭）。描述符可 JSON 序列化、可缓存、可展示在端口视图。

---

## 6. Agent 子系统

### 6.1 组件

|组件|职责|
| ------| ----------------------------------------------------------------------------------------|
|`LLMProxy`|运行在服务/主机侧，按配置名读取原始 key，向允许的 OpenAI 兼容端点签发请求；pi/沙箱只拿本地代理地址与配置名，原始 key 不进入沙箱 env、stdout、trace。代理解决密钥与端点边界，不等于内容防泄漏；发送给 LLM 的 prompt/工具数据仍需最小化|
|`LLMClient`|经 LLMProxy 调用 Chat Completions；流式、重试、用量统计；M0 验证 pi 可配置该本地代理|
|`AgentLoop`|ReAct 循环（US-AGT-03 AC-2）；与具体节点解耦，Pi 节点不用它|
|`ToolProtocol`|`Tool{name, description, parameters, invoke(args) -> str, requires_confirmation}`|
|`ToolDispatcher`|收集 Tool 端口、去重、校验节点工具能力、路由、审计、确认流|
|`NodeTool`|实现 ToolProtocol，仅包装显式授权的节点（§4.3）|
|`SandboxedToolSet`|实现 ToolProtocol × 5（read/write/edit/list/bash），所有操作经 `Sandbox` 接口；bash 仅 Sandboxie 可用，none 仅提供四个受控影子目录文件工具|
|`PiRunner`|子进程运行 pi，注入本地代理地址与配置名，解析输出为轨迹事件|
|`AuditLog`|追加写 `audit.jsonl`；字段名、Authorization、URL userinfo/query 等统一打码|
|`Trace`|每轮请求摘要/响应/工具调用落 `trace.jsonl`；完整 prompt 默认不写，显式开启时配置保留期限|

### 6.2 Agent Loop 伪代码

```python
async def loop(llm, tools, messages, max_turns, on_max_turns, stop_on_text, emit):
    for turn in range(max_turns):
        resp = await llm.chat(messages, tools=schemas(tools), stream=emit.stream)
        messages.append(resp.message)
        if stop_on_text and re.search(stop_on_text, resp.text):
            return Result(messages, stopped_by="stop_pattern", partial=False)
        if not resp.tool_calls:
            return Result(messages, stopped_by="assistant", partial=False)
        for call in resp.tool_calls:
            result = await dispatcher.invoke(call)      # 含确认、审计、超时、错误转文本
            messages.append(tool_message(call.id, result))
            emit.tool_call(call, result)
    if on_max_turns == "return_partial":
        return Result(messages, stopped_by="max_turns", partial=True)
    raise MaxTurnsExceeded(messages)
```

没有 LangChain/LangGraph（D-04）。

### 6.3 人工确认流

`ToolDispatcher.invoke` 发现 `requires_confirmation` → 创建 `ConfirmRequest(id, run_id, tool, args)` → 推送 WS `node.confirm_request` → Run 状态 `waiting` → `await request.future`（超时按 reject）→ 用户经 `POST /api/runs/{id}/confirm` 填充 future → 继续。等待期间引擎其他并行节点不受影响。

---

## 7. 沙箱子系统

### 7.1 接口

```python
class Sandbox(Protocol):
    def spawn(self, cmd: list[str], cwd: Path, env: dict, timeout: float) -> SandboxProcess
    def read_file(self, path: Path) -> bytes
    def write_file(self, path: Path, data: bytes) -> None
    def list_dir(self, path: Path, pattern: str | None) -> list[Entry]
    def collect_changes(self) -> list[Change]
    def apply(self, paths: list[Path]) -> list[ApplyResult]
    def discard(self) -> None
```

`read/write/list` 都通过 `spawn` 一个沙箱内的小 helper 进程（`python -m weft.sandbox.helper <op>`）实现，保证"写入在沙箱内"这一不变量，而不是服务进程直接写沙箱目录（后者绕过了 Sandboxie 的删除标记等语义）。

### 7.2 SandboxieSandbox

- **Run 归属**：每 Run 动态创建独立 `WeftBox-<run_id>`，持久登记 `{run_id, box, root, owned_pids, process_created_at}`。M0 必须实测 box 创建、删除、列举、终止及进程归属；清理只针对登记匹配的本 Run box/进程树，禁止按写入时间或路径猜测，也不终止用户既有 box。
- `spawn`：`Start.exe /box:<box> /wait /silent /env:WEFT_RUN_ID=<id> <cmd>`；stdout/stderr 经临时文件回传。环境变量只含运行标识、本地 LLM 代理地址与配置名，不含原始 API key。
- **基线与收集**：Run 前记录 Root 和显式授权目录的真实文件存在性、内容 SHA-256；Run 后遍历本 Run box 的 `drive\` 映射与删除标记并对比基线。重命名优先按删除+创建的内容哈希匹配，无法可靠判断时降级为删除+创建并提示。
- **审计边界**：v1 只审计 Root 与显式授权目录，其他写入默认拒绝。`user\`（AppData 等）不受支持；若发现未知变化，设置 `audit_complete: false` 并在 UI 明示“审计不完整”，不得静默忽略。
- `apply`：逐项重算目标哈希；与基线不同返回 `CHANGE_CONFLICT`，需用户查看新 diff 后显式覆盖。覆盖/删除前备份，创建/修改用临时文件+rename，deleted 用回收站。逐项记录 `pending/applied/conflict/failed/discarded`，重复 apply 幂等；普通路径不保证多文件事务全原子，protected 路径仍整体拒绝。
- **网络**：默认拒绝沙箱网络，唯一内置例外是本 Run 指定的环回 LLMProxy 地址；该例外只能经代理访问配置的 LLM 端点，不能访问任意主机服务。其他联网必须由用户显式开启并配置、验证有效的网络白名单/防火墙；不得把 Sandboxie 的默认可联网当作安全边界。

### 7.3 NoneSandbox

- 仅用于 CI 与显式允许的审批流模拟。`read/write/edit/list` 由受控 helper 实现，`write/delete` 写到影子目录 `<root>/.runs/<run_id>/shadow/`（而非真实路径），`collect_changes` 比对影子目录。`spawn` 不作为任意命令能力暴露，bash 与 pi 在 `none` 下拒绝运行，避免直接子进程绕开影子目录。
- 全局开关为 `sandbox.allow_none_sandbox: false`；它只允许上述模拟语义，不表示允许无隔离直写。真正“直接写真实路径”的模式不提供。

### 7.4 受保护文件

`workflow.json`、`pyproject.toml`、`uv.lock`、`.runs/**`、`%APPDATA%/weft/**` 的变更标记 `protected`，`apply` 拒绝（US-SBX-05 AC-4）。

---

## 8. 触发器子系统

```
TriggerManager
 ├ ManualSource    —— API/CLI 直接调用
 ├ ChatSource      —— REST POST /chat；WS 仅推送
 ├ ScheduleSource  —— APScheduler (AsyncIOScheduler)，每个 workflow 的 schedule 为 job
 ├ WatchSource     —— watchdog Observer，每个 watch 配置一个 handler，防抖合并
 └ HttpSource      —— FastAPI 路由 + Bearer token 校验 + 限速
```

- 所有 Source 产出统一 `TriggerEvent{source, ts, session_id?, payload}`（US-TRG-01），投入 Engine 执行接口。`source: excel` 仅作 v2 兼容预留，v1 不接受运行。
- Engine 按工作流 `concurrency_policy` 决定入队/丢弃/取消前者（US-EXE-13），每个 Run 入队即冻结快照。立即执行/入队返回 202 与 `disposition: started|queued`；drop 不创建 Run，返回 200 与 `run_id: null`；队列满返回 409。手动、聊天与 HTTP 触发共用此契约。
- `HTTP Response` 每次 Run 最多执行一个，向同步 HTTP 触发提供 `{status_code, headers, body}`；未执行返回 `{}`，执行多个则运行失败。异步触发不等待该节点。
- Trigger 节点 params 是唯一真源；`TriggerManager.activate(workflow)` 在加载时派生运行视图，配置变更时重建，不读取顶层影子 trigger。
- 防自激（US-TRG-05 AC-5）：Run 活跃期间，引擎把所有写出路径上报 `WatchSource.suppress(path, ttl=debounce*2)`。

---

## 9. 前端架构

|层|选择|说明|
| ----------| ----------------------------------------------------| ----------------------------------------------------------------|
|框架|React 18 + TypeScript + Vite||
|画布|@xyflow/react (React Flow 12)|自定义节点组件：状态条、端口颜色、内嵌 Table View|
|状态|Zustand|`workflowStore`（图编辑，含 undo 栈）、`runStore`（执行状态，由 WS 驱动）、`settingsStore`|
|数据获取|TanStack Query|REST 封装；启动 URL 的随机会话令牌只存 sessionStorage，REST 用 Bearer，WS 先 authenticate 再订阅|
|表格预览|TanStack Table + Arrow JS (`apache-arrow`)|端口视图直接消费 Arrow IPC 流；无 sort_by 时按 record batch 分页，指定排序时 v1 允许全量稳定排序，不预建索引|
|表单|JSON Schema → 表单（`@rjsf` 或自研轻量版，开发期定）|节点参数表单自动生成（US-DES-04）|
|diff|`react-diff-view`|变更审批面板|
|聊天|自研轻组件 + `react-markdown`||

原则：**前端无业务规则**。端口兼容性、表达式校验、Loop 配对等一律后端判定，前端只渲染结果（US-DES-03 AC-5）。编辑操作本地乐观更新 + 自动保存防抖 2 s 提交（US-DES-07）。Host/Origin 与 UI 会话令牌均由服务端校验，`X-Weft-Client` 不构成鉴权。

## 10. 可观测性

- 结构化日志（loguru → JSON lines）：服务日志与 Run 日志分离，`trace_id = run_id` 关联（US-SET-03）。
- WS 事件即遥测：`node.started/finished` 自带时长；Run 汇总 usage（US-AGT-10）。
- `DEBUG` 级别记录每次 COM 调用方法名与耗时、LLM 请求摘要。
- 不接外部 APM；v1 单机，日志文件足够。

## 11. 架构决策记录（ADR）

PRD D-01..D-13 之外，本文新增：

|ID|决策|理由|否决的备选|
| ------| ----------------------------------------------------| ----------------------------------------------------------------| --------------------------------------------------------------------------|
|A-01|Worker IPC 用 JSON-RPC over stdio + Arrow IPC 文件 + memory-map|无端口占用；行协议易调试；减少大数据复制，不掩盖序列化/写盘/转换成本|gRPC（重）、socket（端口管理）、共享内存（复杂度不值）|
|A-02|ExcelWorker 放服务进程|Excel 是全局资源须跨 Run 串行；隐藏实例生命周期须比单个 Run 长|放 Workflow Worker（孤儿实例、多队列竞争）|
|A-03|每 Run 懒启动独立 Worker pool，默认 4，结束全部退出|真实子进程并行；隔离崩溃和 run_id/全局状态泄漏|单 Worker 串行、跨 Run 保活、节点级进程（启动开销大）|
|A-04|Loop 以"折叠为虚拟节点 + 递归子图执行"实现|保持顶层 DAG 不变式，调度器简单|通用环图执行器（状态机复杂度大增，v1 不需要）|
|A-05|Metanode 画布概念，引擎展开|引擎少一种容器语义|引擎原生嵌套（缓存键、作用域复杂化）|
|A-06|沙箱 read/write 经沙箱内 helper 进程|保证"写入必在沙箱内"不变量；语义与 bash 工具一致|服务进程直写沙箱目录（绕过 Sandboxie 语义，删除标记不可见）|
|A-07|NoneSandbox 只提供受控影子目录文件工具，禁用任意 bash/pi，不提供直写模式|CI 可测审批流；避免直接子进程绕过影子目录或"关掉沙箱=裸奔"的误用|直写真实路径、混合影子文件工具与任意 spawn|
|A-08|前端零业务规则|规则单点维护在后端；AC 可测|前后端双实现（必然漂移）|
|A-09|表单由 JSON Schema 生成|节点作者只写 schema；UI 自动获得|每节点手写表单组件（节点数量 × 维护成本）|
|A-10|Arrow 贯穿 引擎-Worker-前端 三层|一种表格格式走到底，预览不经 JSON 转换|后端 Arrow + 前端 JSON（大表预览慢、类型丢失）|
|A-11|本机 UI/API/WS 使用随机会话令牌，并校验 Host/Origin|覆盖跨站请求与 DNS rebinding；`X-Weft-Client` 不作为权限控制|本机完全免鉴权、仅检查自定义头|

## 12. 风险与缓解

|风险|影响|缓解|
| ------------------------------------------------------------| ----------------------| --------------------------------------------------------------------------------------|
|Sandboxie 变更收集、归属与外泄|漏报、误杀其他 Run、数据外泄|M0 验证独立 box、owned 进程树、重命名、网络默认拒绝、未知路径；只审计 Root/授权目录，未知变化必须 audit_complete=false|
|xlwings attach 多实例行为|连错实例|M0 实测；提供 PID/窗口/工作簿实例列表，由用户选择，不假设 GetActiveObject 是最近活动实例|
|COM 调用不可中断|取消不即时、队列阻塞|超时只放弃请求；Worker 保持繁忙，后续排队；UI 明确提示，fast_mode 仅作受控优化|
|pi CLI 与密钥代理兼容性|Pi 节点脆弱或 key 泄漏|M0 验证本地 OpenAI 兼容 LLMProxy；版本检测；key 不下发，解析失败降级为原文透传|
|JSON Schema 表单库对复杂参数（条件显隐、列名联动）支持不足|节点配置体验差|允许节点声明 `ui_hints`；个别复杂节点允许自定义面板组件（逃生舱）|
|mock LLM 与真实模型行为差异|AC 通过但真实不可用|`[manual]` 验收层保留；录制真实响应作为回放测试素材|

## 13. v2 预留（不实现，仅不堵路）

- **Runner**：Workflow Worker 协议不变，传输从 stdio 换为 WebSocket + 文件上传；`ValueRef` 已含内容哈希可做增量传输。
- **xlOil 伴侣插件**：触发事件结构已含 `source: excel`；插件经 HTTP 触发端点回调。
- **桌面壳**：pywebview/Tauri 包一层，服务进程不变。
- **PyO3 引擎热点替换**：调度器与缓存键计算是纯函数，接口稳定后可逐个替换。  
