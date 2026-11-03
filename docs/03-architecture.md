# 03-architecture.md

**Weft 架构设计文档**

|项|值|
| ------| -----------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`01-prd.md`​（§9 约束、§10 决策）、​`02-user-stories.md`|
|下游|`04-data-model.md`​、​`05-api.md`​、​`07-engineering.md`|

本文回答"系统怎么拆、进程怎么分、数据怎么流、为什么这样"。与 PRD 决策记录（D-01..D-13）重复的理由不再展开，只引用编号。

---

## 1. 总览

### 1.1 进程拓扑

```
┌─────────────────────────── 用户机器（Windows，登录会话） ───────────────────────────┐
│                                                                                    │
│  浏览器 (React + React Flow)                                                        │
│      │  HTTP / WebSocket (127.0.0.1:7788)                                          │
│      ▼                                                                             │
│  ┌──────────────────── weft 服务进程（Weft 自带环境） ────────────────────┐          │
│  │  FastAPI (REST + WS)                                                 │          │
│  │  WorkflowStore        —— workflow.json 读写、校验、迁移                │          │
│  │  Engine               —— 调度器：拓扑排序、状态机、缓存、Run 队列        │          │
│  │  TriggerManager       —— schedule / watch / http / chat / manual      │          │
│  │  ExcelWorker (STA 线程) —— 全局唯一，所有 COM 调用串行于此              │◄─┐       │
│  │  SandboxManager       —— spawn / collect_changes / apply              │  │       │
│  │  AgentRuntime         —— Agent Loop、LLM 客户端、工具分发              │  │       │
│  └───────┬──────────────────────────────┬───────────────────────────────┘  │ COM    │
│          │ JSON-RPC over stdio           │ Start.exe /box:WeftBox           │        │
│          │ + Arrow IPC 文件               │                                  │        │
│          ▼                               ▼                                  │        │
│  ┌──────────────────┐          ┌───────────────────────┐          ┌─────────┴─────┐ │
│  │ Workflow Worker   │          │  Sandboxie: WeftBox   │          │ Excel.exe     │ │
│  │ (<root>/.venv)    │          │  ├ sandboxed tools    │          │ (用户可见实例  │ │
│  │ 执行节点用户代码/   │          │  │  (read/write/bash) │          │  或隐藏实例)   │ │
│  │ Polars 计算       │          │  └ pi agent 子进程     │          └───────────────┘ │
│  └──────────────────┘          └───────────────────────┘                            │
└────────────────────────────────────────────────────────────────────────────────────┘
                 │ HTTPS
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
├── engine/         # 调度器、Run 状态机、缓存、循环/分支语义
├── nodes/          # 节点注册表、节点类型定义（声明 + 可信车道实现）
├── excel/          # ExcelBackend 接口、XlwingsBackend、FakeBackend、ExcelWorker
├── agent/          # LLM 客户端、Agent Loop、工具协议、审计
├── sandbox/        # Sandbox 接口、NoneSandbox、SandboxieSandbox、变更收集
├── triggers/       # TriggerManager 与 5 种触发源
├── workflow/       # workflow.json 模型、校验、迁移、打包
├── worker/         # Workflow Worker 入口与 RPC 协议（也被 .venv 侧复用）
└── cli/            # weft serve/run/pack/unpack/doctor
```

依赖方向（只允许向下）：​`api → engine → {nodes, excel, agent, sandbox, triggers} → workflow`​。​`worker`​ 是独立可执行模块，仅依赖 ​`nodes` 的声明部分与 RPC 协议。

---

## 2. 执行引擎

这是整个项目的核心资产（D-02）。

### 2.1 图模型

- 图 = 节点 + 有向边；边连接 ​`(node, output_port) → (node, input_port)`。
- 顶层图必须是 **DAG**，唯一例外是 ​`Loop Start → ... → Loop End` 区域：引擎在加载时识别成对的 Loop 节点，把中间子图折叠为一个"虚拟循环节点"后再做拓扑排序。折叠后仍非 DAG 则拒绝运行。
- Metanode 在加载时**内联展开**（节点 ID 加前缀 ​`meta_<id>/`），引擎不感知 Metanode，只有画布感知。
- 端口类型见 ​`04-data-model.md` §3；引擎只关心类型兼容与"值如何序列化到缓存"，不关心值的语义。
- 每个节点声明 ​`execution_lane`​：​`trusted_worker`​（默认，在 Workflow Worker 执行）、​`trusted_service`​（在服务进程执行，用于 Excel、Agent、触发器等需要访问服务内单例的节点）、​`sandboxed`（节点本身不执行，只是向 agent 提供沙箱工具）。

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

节点状态机（与 UI 三态灯对应）：

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
    while ready or inflight:
        for n in list(ready):
            if n not in scope: mark(n, skipped_by_scope); continue
            if cache_hit(n): mark(n, executed_from_cache); release_downstream(n); continue
            inflight.add(spawn(execute(n)))
        done = await wait_any(inflight)
        for n in done:
            if n.failed and not inside_try(n): cancel_all(); return FAILED
            release_downstream(n)                  # 分支节点只释放命中的下游
```

- **ExecScope**：由"整体运行 / 执行到此 / 从此开始 / 仅本节点"计算出的节点集合（​`02-user-stories.md` US-EXE-02/03）。
- **并行度**：​`trusted_worker`​ 节点默认并行上限 4（可配）；​`trusted_service` 中 Excel 节点由 ExcelWorker 天然串行；Agent 节点并行上限 2（LLM 限速考虑）。
- **分支**：​`If/Switch`​ 执行后向引擎返回 ​`activated_ports`​；未激活端口的下游整条链标记 ​`skipped`​，​`Merge`​ 类节点声明 ​`accepts_partial_inputs=True` 才能在部分输入 skipped 时执行。
- **循环**：虚拟循环节点内部是一个递归的 ​`run(subgraph, scope=all)`​，每次迭代使用独立的 ​`IterationContext(index, total)`，缓存键混入迭代号（US-EXE-10 AC-4）。循环体内禁止再出现 Trigger。

### 2.4 缓存

|项|规则|
| ----------| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|键|`sha256(node_type ‖ node_version ‖ canonical_json(resolved_params) ‖ Σ input_port_hash)`​；​`resolved_params`​ 是流变量注入**之后**的参数|
|输入哈希|Table：Arrow IPC 文件的 sha256（写入时计算并存于 sidecar ​`.meta.json`​）；Variable/Message：canonical JSON 哈希；Excel 描述符：描述符 JSON 哈希（不含 COM 对象）；文件类参数：​`path ‖ mtime ‖ size`|
|位置|`<root>/.runs/cache/<node_id>/<port>.{arrow,json}`​ + ​`<node_id>/meta.json`（含键、node_version、写入时间）|
|失效|键不匹配；meta 缺失或损坏；Excel 描述符重新解析失败（US-XLS-11 AC-4）；用户"重置"|
|清理|"重置全部"清空；超过 ​`cache_max_mb`（默认 2 GB）按 LRU 删除|

Excel 引用缓存的特殊处理（PRD Q1 的答案）：缓存中只存描述符；缓存命中时 ExcelWorker 按描述符 ​`resolve()`，解析不到（用户关了工作簿）则把该节点及下游标记为 configured 并重跑。

### 2.5 取消

- Run 级 ​`asyncio.CancelledError` 传播到所有 inflight 节点。
- `trusted_worker`​ 节点：向 Worker 发送 ​`cancel(node_exec_id)`​ RPC；Worker 在用户代码中通过 ​`weft_ctx.check_cancelled()`​ 协作取消；3 s 后未响应则 ​`CTRL_BREAK_EVENT`​，再 3 s 后 kill 并**重启 Worker 进程**（后续节点无法执行，Run 已经终止所以无影响）。
- Agent 节点：取消 HTTP 流；当前轮返回后不再发起。
- Excel 节点：COM 调用无法中断，等待当前调用返回（受 ​`excel_call_timeout` 约束），然后放弃结果。
- 沙箱进程：​`Start.exe /box:X /terminate`。

---

## 3. Workflow Worker 与 IPC（PRD Q4 的答案）

### 3.1 为什么要独立进程

- 用户依赖在 ​`<root>/.venv`，与 Weft 本体环境隔离（D-09，US-EXE-14）。
- 用户代码崩溃（段错误、死循环）不拖垮服务。
- 为 v2 Runner 预留：Runner 就是"远端的 Workflow Worker"，协议不变。

### 3.2 协议

**传输**：子进程 stdio，每行一个 JSON（JSON-RPC 2.0 子集）；stderr 作为日志通道。不用 socket，减少端口与防火墙问题。

**大数据不走 stdio**：Table 值以 Arrow IPC 文件传递，RPC 中只传路径。文件位于 ​`<root>/.runs/<run_id>/ipc/<node_exec_id>/<port>.arrow`​，Worker 端 ​`pa.memory_map` 读取（零拷贝）。节点输出同样写文件后返回路径，引擎再决定是否提升为缓存（rename，不拷贝）。

**方法**：

|方向|方法|说明|
| ------| ------| -----------------------------------------|
|S→W|`init(root, run_id, node_types_manifest)`|启动后握手，Worker 加载 ​`nodes/` 下用户节点|
|S→W|`execute(node_exec_id, node_type, params, inputs: {port: ValueRef}, ctx)`|返回 ​`{outputs: {port: ValueRef}, activated_ports?}`|
|S→W|`cancel(node_exec_id)`||
|S→W|`shutdown()`||
|W→S|`log(node_exec_id, level, message)`|通知（无需响应）|
|W→S|`progress(node_exec_id, fraction, message?)`|通知|
|W→S|`tool_call(node_exec_id, tool, args)`|**预留**：v1 不用（Agent 在服务进程）|

`ValueRef`​ 定义见 ​`04-data-model.md` §4。

**生命周期**：一个 Run 一个 Worker 进程（US-EXE-14 AC-3）；Run 结束后保留 60 s 空闲以加速连续局部执行，超时退出；​`pyproject.toml`​/​`nodes/` 变化后下一次 Run 强制重启。

### 3.3 Worker 侧 SDK（​`weft_ctx`）

用户 Python 节点与自定义节点可用的最小 API：

```python
weft_ctx.root: Path                 # 工作流 Root 绝对路径
weft_ctx.run_id: str
weft_ctx.vars: dict                 # 流变量（只读视图）
weft_ctx.log(msg, level="INFO")
weft_ctx.progress(fraction, msg=None)
weft_ctx.check_cancelled()          # 抛 weft_ctx.Cancelled
weft_ctx.resolve(path) -> Path      # 相对 Root 解析
```

`weft_ctx`​ 由 ​`weft-sdk`​ 包提供（纯 Python，无重依赖），是工作流 ​`pyproject.toml` 的基础依赖之一（US-EXE-14 AC-5）。

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
    inputs = [Port("in", PortType.TABLE)]
    outputs = [Port("out", PortType.TABLE)]
    params_schema = {...}            # JSON Schema draft 2020-12
    portable_params = ["path"]       # 标记 format: weft-path 的字段（打包检查）
    external_resources = []          # 运行前预检（US-PKG-07）

    def execute(self, ctx: NodeContext, inputs: dict, params: dict) -> dict:
        ...
```

- **声明部分**（type、version、ports、schema）在服务进程与 Worker 两侧都可加载，用于 UI 表单生成、校验、缓存键；**实现部分**只在声明的 lane 对应的进程中加载。
- 注册表：内置节点通过包内扫描；用户节点通过 ​`<root>/nodes/*.py`​ 中的 ​`@weft.node` 装饰器注册，仅对该工作流可见。
- 节点 ​`execute`​ 对 Table 端口接收/返回 ​`polars.DataFrame`，框架负责 Arrow 转换（US-TBL-01 AC-1）。
- 节点通过 ​`ctx`​ 访问日志、进度、取消、Root、以及（仅 ​`trusted_service`​ lane）​`ctx.excel`​、​`ctx.llm`​、​`ctx.sandbox` 服务句柄。

### 4.2 节点分类与 lane

|分类|lane|原因|
| -----------------------------------------------------------------------| ------------------------| ----------------------------------------------|
|表格、文件、Python Script、Shell|`trusted_worker`|需要用户依赖；可能很重|
|Excel|`trusted_service`|必须经 ExcelWorker（§5）|
|Agent（LLM Call、Agent Loop、Pi、Node as Tool、Prompt、Memory、Chat）|`trusted_service`|需要 LLM 客户端、审计、WS 流式推送、工具分发|
|Sandboxed Tools|`sandboxed`（声明性，不执行）|提供工具给 Agent|
|流程（Trigger、If、Switch、Loop、Try、Variable、Merge、Wait）|`trusted_service`|引擎语义节点，轻量|

`trusted_service` 节点若需要 Table 输入，服务进程读取 Arrow 文件（服务本体环境自带 pyarrow/polars）。

### 4.3 Node as Tool 的执行路径

```
Agent Loop (service) ─tool_call─► ToolDispatcher ─► NodeTool.invoke(args)
     │                                                   │
     │                                     构造临时 exec：params = 目标节点参数 ⊕ args
     │                                     inputs = 目标节点上游的缓存值
     │                                                   ▼
     │                                   engine.execute_single(node, params, inputs, ephemeral=True)
     │                                                   │（按节点 lane 路由到 Worker 或 service）
     ◄──────────────── result_format 转字符串 ◄──────────┘
                       + 审计日志
```

`ephemeral=True` 表示不写缓存、不改变画布状态。

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

实现：​`XlwingsBackend`​（v1）、​`FakeExcelBackend`（内存实现，CI 用）。xlOil 后端 v2 考虑。

### 5.2 ExcelWorker

- 服务进程内的**单例线程**，线程启动时 ​`pythoncom.CoInitialize()`（STA）。
- 所有 ​`ExcelBackend`​ 调用通过 ​`await worker.submit(fn, *args)`​，内部为 ​`queue.Queue`​ + ​`concurrent.futures.Future`。
- 放在服务进程而非 Workflow Worker 的原因：

  1. 用户可见 Excel 实例是**全局资源**，多工作流共享一条串行队列（US-EXE-13 AC-3）。
  2. Workflow Worker 一个 Run 一个，COM 连接随进程生死会导致隐藏实例成为孤儿。
  3. Node as Tool 调 Excel 节点时与 Agent 同在服务进程，路径最短。
- 代价：服务进程环境必须含 ​`xlwings`​ + ​`pywin32`​，非 Windows 时这两者为可选依赖，​`XlwingsBackend`​ 不可用则自动降级 ​`FakeExcelBackend`​ 并在 ​`doctor` 中报告。
- 引用管理：​`RefRegistry`​ 维护 ​`描述符 → COM 对象`​，Run 结束后释放该 Run 创建的引用（attach 的可见实例不关闭；​`new_hidden` 按参数关闭）。
- 超时：​`submit` 带 timeout；超时后 Future 标记放弃，线程继续执行该调用直到返回（COM 不可中断），期间后续任务排队——这是 COM 的固有限制，UI 提示用户检查 Excel 窗口。
- 错误映射：​`pywintypes.com_error`​ 的 HRESULT → 可读错误（​`0x800AC472` 等 → "Excel is busy"），见 US-XLS-12。

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
|`LLMClient`|OpenAI 兼容 Chat Completions；流式；重试（429/5xx 指数退避）；用量统计；按配置名实例化|
|`AgentLoop`|ReAct 循环（US-AGT-03 AC-2）；与具体节点解耦，Pi 节点不用它|
|`ToolProtocol`|`Tool{name, description, parameters, invoke(args) -> str, requires_confirmation}`|
|`ToolDispatcher`|收集 Tool 端口的所有工具、去重校验、路由调用、审计、确认流|
|`NodeTool`|实现 ToolProtocol，包装节点（§4.3）|
|`SandboxedToolSet`|实现 ToolProtocol × 5（read/write/edit/list/bash），所有操作经 ​`Sandbox` 接口|
|`PiRunner`|子进程运行 pi，解析其输出为轨迹事件|
|`AuditLog`|追加写 ​`audit.jsonl`，打码|
|`Trace`|每轮请求/响应/工具调用落 ​`trace.jsonl`，供 UI 轨迹面板|

### 6.2 Agent Loop 伪代码

```python
async def loop(llm, tools, messages, max_turns, stop_on_text, emit):
    for turn in range(max_turns):
        resp = await llm.chat(messages, tools=schemas(tools), stream=emit.stream)
        messages.append(resp.message)
        if not resp.tool_calls:
            return Result(messages, stopped_by="assistant")
        for call in resp.tool_calls:
            result = await dispatcher.invoke(call)      # 含确认、审计、超时、错误转文本
            messages.append(tool_message(call.id, result))
            emit.tool_call(call, result)
        if stop_on_text and re.search(stop_on_text, resp.text): 
            return Result(messages, stopped_by="stop_pattern")
    return Result(messages, stopped_by="max_turns")
```

没有 LangChain/LangGraph（D-04）。

### 6.3 人工确认流

`ToolDispatcher.invoke`​ 发现 ​`requires_confirmation`​ → 创建 ​`ConfirmRequest(id, run_id, tool, args)`​ → 推送 WS ​`node.confirm_request`​ → Run 状态 ​`waiting`​ → ​`await request.future`​（超时按 reject）→ 用户经 ​`POST /api/runs/{id}/confirm` 填充 future → 继续。等待期间引擎其他并行节点不受影响。

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

`read/write/list`​ 都通过 ​`spawn`​ 一个沙箱内的小 helper 进程（​`python -m weft.sandbox.helper <op>`）实现，保证"写入在沙箱内"这一不变量，而不是服务进程直接写沙箱目录（后者绕过了 Sandboxie 的删除标记等语义）。

### 7.2 SandboxieSandbox

- `spawn`​：​`Start.exe /box:<box> /wait /silent /env:WEFT_RUN_ID=<id> <cmd>`；stdout/stderr 经临时文件回传（Sandboxie 对管道继承不可靠）。
- `collect_changes`​：遍历 ​`<sandbox root>\drive\<X>\...`​ 与 ​`<sandbox root>\user\...`​，对每个文件与真实路径比对：真实不存在 → created；存在且哈希不同 → modified；Sandboxie 删除标记（​`*.deleted`​ 记录或 ​`RegHive`​/​`FileSystem`​ 日志）→ deleted。v1 只处理 ​`drive\`​ 映射，​`user\` 下（AppData 等）忽略并记日志。
- `apply`​：逐文件复制到真实路径（先写临时文件再 rename）；deleted → ​`send2trash`。
- 并发：v1 全局一个 box，同一时刻一个使用沙箱的 Run（US-SBX-02 AC-3），​`SandboxManager` 持锁。
- 网络：Sandboxie 默认允许网络；​`doctor` 验证。

### 7.3 NoneSandbox

- 用于 CI 与显式允许的场景。​`spawn`​ 直接子进程；​`write/delete`​ 写到影子目录 ​`<root>/.runs/<run_id>/shadow/`​（而非真实路径），​`collect_changes` 比对影子目录——这样审批流在无 Sandboxie 的环境也可测试。真正"直接写真实路径"的模式不提供（PRD 安全原则）。

### 7.4 受保护文件

`workflow.json`​、​`pyproject.toml`​、​`uv.lock`​、​`.runs/**`​、​`%APPDATA%/weft/**`​ 的变更标记 ​`protected`​，​`apply` 拒绝（US-SBX-05 AC-4）。

---

## 8. 触发器子系统

```
TriggerManager
 ├ ManualSource    —— API/CLI 直接调用
 ├ ChatSource      —— WS 聊天消息
 ├ ScheduleSource  —— APScheduler (AsyncIOScheduler)，每个 workflow 的 schedule 为 job
 ├ WatchSource     —— watchdog Observer，每个 watch 配置一个 handler，防抖合并
 └ HttpSource      —— FastAPI 路由 + Bearer token 校验 + 限速
```

- 所有 Source 产出统一 ​`TriggerEvent{source, ts, payload, session_id?}`​（US-TRG-01），投入 ​`Engine.submit(workflow_id, event)`。
- Engine 按工作流的 ​`concurrency_policy` 决定入队/丢弃/取消前者（US-EXE-13）。
- 工作流打开时 ​`TriggerManager.activate(workflow)`​ 注册 schedule/watch；关闭或配置变更时重建。配置热更新：监听 ​`workflow.json` 的 trigger 段变化。
- 防自激（US-TRG-05 AC-5）：Run 活跃期间，引擎把所有写出路径上报 ​`WatchSource.suppress(path, ttl=debounce*2)`。

---

## 9. 前端架构

|层|选择|说明|
| ----------| ----------------------------------------------------| ----------------------------------------------------------------|
|框架|React 18 + TypeScript + Vite||
|画布|@xyflow/react (React Flow 12)|自定义节点组件：状态条、端口颜色、内嵌 Table View|
|状态|Zustand|`workflowStore`​（图编辑，含 undo 栈）、​`runStore`​（执行状态，由 WS 驱动）、​`settingsStore`|
|数据获取|TanStack Query|REST 封装；WS 事件直接写 runStore|
|表格预览|TanStack Table + Arrow JS (​`apache-arrow`)|端口视图直接消费 Arrow IPC 流，不经 JSON|
|表单|JSON Schema → 表单（​`@rjsf` 或自研轻量版，开发期定）|节点参数表单自动生成（US-DES-04）|
|diff|`react-diff-view`|变更审批面板|
|聊天|自研轻组件 + ​`react-markdown`||

原则：**前端无业务规则**。端口兼容性、表达式校验、Loop 配对等一律后端判定，前端只渲染结果（US-DES-03 AC-5）。编辑操作本地乐观更新 + 自动保存防抖 2 s 提交（US-DES-07）。

## 10. 可观测性

- 结构化日志（loguru → JSON lines）：服务日志与 Run 日志分离，​`trace_id = run_id` 关联（US-SET-03）。
- WS 事件即遥测：​`node.started/finished` 自带时长；Run 汇总 usage（US-AGT-10）。
- `DEBUG` 级别记录每次 COM 调用方法名与耗时、LLM 请求摘要。
- 不接外部 APM；v1 单机，日志文件足够。

## 11. 架构决策记录（ADR）

PRD D-01..D-13 之外，本文新增：

|ID|决策|理由|否决的备选|
| ------| ----------------------------------------------------| ----------------------------------------------------------------| --------------------------------------------------------------------------|
|A-01|Worker IPC 用 JSON-RPC over stdio + Arrow IPC 文件|无端口占用；行协议易调试；大数据零拷贝走文件映射|gRPC（重、Windows 证书麻烦）、socket（端口管理）、共享内存（复杂度不值）|
|A-02|ExcelWorker 放服务进程|Excel 是全局资源须跨 Run 串行；隐藏实例生命周期须比单个 Run 长|放 Workflow Worker（孤儿实例、多队列竞争）|
|A-03|一个 Run 一个 Worker 进程，空闲保活 60 s|隔离崩溃；连续调试快|节点级进程（启动开销大）、常驻单 Worker（依赖变更需手动重启）|
|A-04|Loop 以"折叠为虚拟节点 + 递归子图执行"实现|保持顶层 DAG 不变式，调度器简单|通用环图执行器（状态机复杂度大增，v1 不需要）|
|A-05|Metanode 画布概念，引擎展开|引擎少一种容器语义|引擎原生嵌套（缓存键、作用域复杂化）|
|A-06|沙箱 read/write 经沙箱内 helper 进程|保证"写入必在沙箱内"不变量；语义与 bash 工具一致|服务进程直写沙箱目录（绕过 Sandboxie 语义，删除标记不可见）|
|A-07|NoneSandbox 用影子目录模拟，不提供直写模式|CI 可测审批流；避免"关掉沙箱=裸奔"的误用|直写真实路径|
|A-08|前端零业务规则|规则单点维护在后端；AC 可测|前后端双实现（必然漂移）|
|A-09|表单由 JSON Schema 生成|节点作者只写 schema；UI 自动获得|每节点手写表单组件（节点数量 × 维护成本）|
|A-10|Arrow 贯穿 引擎-Worker-前端 三层|一种表格格式走到底，预览不经 JSON 转换|后端 Arrow + 前端 JSON（大表预览慢、类型丢失）|

## 12. 风险与缓解

|风险|影响|缓解|
| ------------------------------------------------------------| ----------------------| --------------------------------------------------------------------------------------|
|Sandboxie 变更收集的准确性（删除标记、注册表、特殊路径）|审批列表漏报/误报|M1 做技术 spike 验证；v1 范围缩小到 ​`drive\` 下文件；审批 UI 明示"Root 外变更可能不完整"|
|xlwings attach 多实例行为（GetActiveObject 只拿到一个）|连错实例|描述符带 pid；UI 显示连接目标；文档注明多实例限制|
|COM 调用不可中断|取消不即时、队列阻塞|超时放弃 + UI 提示；fast_mode 缩短调用时长|
|pi CLI 的输出格式/参数不稳定|Pi 节点脆弱|PiRunner 隔离解析逻辑；版本检测；解析失败降级为原文透传|
|JSON Schema 表单库对复杂参数（条件显隐、列名联动）支持不足|节点配置体验差|允许节点声明 ​`ui_hints`；个别复杂节点允许自定义面板组件（逃生舱）|
|mock LLM 与真实模型行为差异|AC 通过但真实不可用|`[manual]` 验收层保留；录制真实响应作为回放测试素材|

## 13. v2 预留（不实现，仅不堵路）

- **Runner**：Workflow Worker 协议不变，传输从 stdio 换为 WebSocket + 文件上传；​`ValueRef` 已含内容哈希可做增量传输。
- **xlOil 伴侣插件**：触发事件结构已含 ​`source: excel`；插件经 HTTP 触发端点回调。
- **桌面壳**：pywebview/Tauri 包一层，服务进程不变。
- **PyO3 引擎热点替换**：调度器与缓存键计算是纯函数，接口稳定后可逐个替换。  
  </parameter>  
  </invoke>

架构文档写完。继续写数据模型与接口契约。

<invoke>Write</invoke>  
<parameter name="file_path">/home/user/weft/docs/04-data-model.md</parameter>  
<parameter name="content"># Weft 数据模型

|项|值|
| ------| -------------------------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`01-prd.md`​ §5 核心概念、​`03-architecture.md`|
|下游|`05-api.md`​、​`06-nodes-v1.md`、实现代码（Pydantic 模型以本文为准）|

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
    ├── cache/<node_id>/{<port>.arrow|<port>.json, meta.json}
    ├── memory/<session_id>.jsonl
    └── <run_id>/
        ├── meta.json          # Run 元数据（§6）
        ├── log.jsonl          # Run 日志
        ├── audit.jsonl        # 审计（§7）
        ├── changes.json       # 沙箱变更（§8）
        ├── ipc/               # Worker 间 Arrow 临时文件
        └── nodes/<node_id>.trace.jsonl
```

路径规则：​`workflow.json`​ 中所有 ​`format: weft-path`​ 字段存**相对 Root 的 POSIX 风格路径**（​`data/in.csv`​）；绝对路径允许但打包时警告。运行时由 ​`weft_ctx.resolve()` 统一解析。

## 2. workflow.json

```jsonc
{
  "schema_version": 1,
  "id": "wf_8f3a...",              // 创建时生成，打包/复制后不变
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
  "trigger": {                          // Trigger 节点的配置（节点 params 的影子，便于 TriggerManager 直读）
    "manual":   {"enabled": true},
    "chat":     {"enabled": false},
    "schedule": {"enabled": false, "schedules": [{"cron": "0 9 * * 1-5"}]},
    "watch":    {"enabled": false, "watches": [{"path": "data/inbox", "pattern": "*.xlsx",
                  "events": ["created"], "debounce_ms": 2000, "recursive": false}]},
    "http":     {"enabled": false, "token_hash": "sha256:..."}   // 原文不落盘
  },
  "variables": [                        // 工作流级默认流变量（可被触发 overrides 覆盖）
    {"name": "target_wb", "type": "str", "value": "汇总.xlsx"}
  ],
  "nodes": [
    {
      "id": "n_a1b2",                  // "n_" + 8 hex
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
    {"id": "e_c3d4", "source": "n_a1b2", "sourcePort": "out",
     "target": "n_e5f6", "targetPort": "in"}
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
|`nodes[].id`​ 唯一；​`edges` 引用的节点与端口存在|ERROR|
|边两端端口类型兼容（§3.3）|ERROR|
|非 Tool/Variable 输入端口入边 ≤ 1|ERROR|
|折叠 Loop 后无环|ERROR|
|Loop Start/End 配对且嵌套合法|ERROR|
|恰好一个 ​`flow.trigger` 节点|ERROR|
|`{"$var": name}` 引用的变量可能存在（静态可达性不保证，运行时兜底）|WARN|
|`format: weft-path` 字段为绝对路径|WARN（打包时汇总）|

## 3. 端口类型系统

### 3.1 六种类型

|类型|值（运行时）|缓存序列化|UI 颜色|语义|
| ------| ----------------------| ------------------------| ---------| ---------------------------------|
|`table`|`pyarrow.Table`|`.arrow`（Arrow IPC file）|蓝 ​`#3b82f6`|结构化表格|
|`excel`|描述符 dict（§3.2）|`.json`|橙 ​`#f97316`|Excel App/Workbook/Range 引用|
|`variable`|`dict[str, Any]`（一组流变量）|`.json`|红 ​`#ef4444`|标量参数集|
|`message`|`list[ChatMessage]`|`.json`|紫 ​`#a855f7`|LLM 消息序列|
|`tool`|`list[ToolDecl]`|不缓存（声明性）|绿 ​`#22c55e`|agent 工具|
|`flow`|无值（仅时序依赖）|不缓存|灰 ​`#9ca3af`|控制流（If/Try 分支、显式顺序）|

`ChatMessage = {role: system|user|assistant|tool, content: str, tool_calls?: [...], tool_call_id?: str, name?: str}`（OpenAI 规范子集）。

`ToolDecl = {name, description, parameters: JSONSchema, kind: node|sandboxed, requires_confirmation: bool, binding: {...}}`​，​`binding` 为实现侧路由信息（目标节点 ID 或沙箱工具名），不暴露给 LLM。

### 3.2 Excel 描述符

见 ​`03-architecture.md`​ §5.3。三种 ​`kind: app | workbook | range`​，均可 JSON 序列化；​`resolve()` 失败即缓存失效。

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

✓* 任何数据端口可连到 ​`flow`​ 输入端口（只取时序，弃值）。除此之外无隐式转换；类型转换一律显式节点（​`Table to Variables` 等）。此矩阵即 US-DES-03 AC-5 的测试表。

### 3.4 流变量作用域

- `variable`​ 端口的值是 dict，沿边流动时**合并**：多条 Variable 入边时按边创建顺序浅合并，后者覆盖前者（UI 提示覆盖项）。
- 节点收到的变量作用域 = 工作流级 ​`variables`​ ⊕ 触发 ​`payload.overrides` ⊕ 所有到达本节点的 variable 端口值（就近优先）。
- `{"$var": name}` 在节点执行前由引擎解析；缺失则节点失败（US-DES-06 AC-4）。

## 4. ValueRef（IPC 与缓存的统一值引用）

```jsonc
{"kind": "table",    "path": ".runs/r_1/ipc/x/out.arrow", "hash": "sha256:...", "rows": 1000, "cols": 5}
{"kind": "json",     "inline": {...}, "hash": "sha256:..."}         // variable / message / excel 描述符
{"kind": "none"}                                                     // flow 端口
```

规则：​`table`​ 永远走文件；JSON 值 ≤ 256 KB 时 ​`inline`​，否则落文件给 ​`path`​。​`hash`​ 用于缓存键（​`03-architecture.md` §2.4）。

## 5. TriggerEvent

```jsonc
{
  "source": "manual | chat | schedule | file | http",
  "ts": "ISO8601",
  "session_id": "s_...",            // chat 必有，其余可空
  "payload": {
    // manual:   {"overrides": {k: v}}
    // chat:     {"message": str, "history_len": int}
    // schedule: {"schedule_id": str, "scheduled_at": ISO8601}
    // file:     {"events": [{"path": str, "kind": "created|modified|deleted", "ts": ISO8601}]}
    // http:     {"body": any, "headers_subset": {...}}
  }
}
```

Trigger 节点输出：​`variable`​ 端口 = ​`{source, ts} ⊕ flatten(payload)`​；​`message`​ 端口 = chat 时 ​`[{role: "user", content: message}]`​ 否则 ​`[]`​；​`table`​ 端口 = file 时 events 表（列 ​`path, kind, ts`）否则空表。

## 6. Run 与节点执行记录

```jsonc
// .runs/<run_id>/meta.json
{
  "run_id": "r_20250101_093000_a1b2",
  "workflow_id": "wf_8f3a...",
  "trigger": { TriggerEvent },
  "scope": {"kind": "all | to_node | from_node | single", "node_id": null},
  "status": "queued | running | waiting | succeeded | failed | cancelled",
  "started_at": "...", "finished_at": "...",
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "llm_calls": 0, "tool_calls": 0},
  "nodes": {
    "n_a1b2": {"status": "executed | failed | ...", "started_at": "...", "finished_at": "...",
                "from_cache": false, "error": {"type": "...", "message": "...", "traceback": "..."} }
  }
}
```

`run_id`​ 格式：​`r_<yyyymmdd>_<hhmmss>_<4hex>`，可排序。

## 7. 审计记录（audit.jsonl，每行一条）

```jsonc
{"ts": "...", "run_id": "...", "node_id": "n_...", "agent_kind": "agent_loop | pi",
 "lane": "trusted | sandboxed", "tool": "excel_read_range",
 "args_redacted": {...}, "status": "ok | error | rejected",
 "duration_ms": 123, "result_hash": "sha256:..."}
```

打码规则：键名匹配 ​`/key|token|password|secret/i`​ 的字符串值替换为 ​`"***"`。

## 8. 变更记录（changes.json）

```jsonc
{
  "run_id": "...", "collected_at": "...",
  "sandbox": "sandboxie | none",
  "changes": [
    {"path": "D:/flows/demo.weft/out/a.txt",       // 真实目标路径（绝对）
     "rel_root": "out/a.txt",                       // Root 内时给出相对路径，否则 null
     "kind": "created | modified | deleted",
     "size": 1024, "is_text": true, "protected": false,
     "applied": false}
  ]
}
```

## 9. 节点类型命名空间

`<namespace>.<name>`​，v1 命名空间：​`flow`​ ​`table`​ ​`excel`​ ​`file`​ ​`agent`​ ​`code`​。用户节点强制 ​`user.<name>`​。完整节点清单与各自 params schema 在 ​`06-nodes-v1.md`。

## 10. 用户级配置（config.toml）

```toml
[server]
host = "127.0.0.1"
port = 7788
open_browser = true
global_token = ""            # 监听非本机时必填

[llm.default]
base_url = "https://api.example.com/v1"
api_key  = "sk-..."
model    = "gpt-4o"
timeout  = 120

[excel]
backend = "xlwings"          # xlwings | fake
call_timeout = 60

[sandbox]
default = "sandboxie"        # sandboxie | none
allow_unsandboxed = false

[sandbox.sandboxie]
start_exe = 'C:\Program Files\Sandboxie-Plus\Start.exe'
box = "WeftBox"

[agent]
pi_path = ""                 # 空 = PATH 查找
confirm_timeout_s = 600

[logging]
level = "INFO"
retention_days = 14

[cache]
max_mb = 2048
```

## 11. 版本与迁移

- `schema_version`​ 整数递增；迁移函数 ​`migrate_v{n}_to_v{n+1}(doc) -> doc`​ 注册于 ​`weft.workflow.migrations`​，逐级执行，迁移前备份 ​`workflow.json.bak.v{n}`。
- 节点级：​`node_version`​ 不匹配时调用节点类的 ​`migrate_params(old_version, params) -> params`；未实现则原样保留并 WARN。
- 未知节点类型：加载为 ​`flow.placeholder`（保留原 type/params，不可执行），保存时原样写回，不丢数据（US-PKG-05 AC-3）。

‍
