# 08-testing-strategy.md

# Weft 测试策略

|项|值|
| ------| -----------------------------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`01-prd.md`（§9.3 性能目标）、`02-user-stories.md`（AC 真源）、`03-architecture.md`、`06-engineering.md`|
|读者|实现代码的 Coding Agent、CI 系统、人工验收者|

---

## 1. 测试目标与核心挑战

### 1.1 本文档要解决什么问题

给 Coding Agent 交办开发任务时，最大的工程风险不是“写不出代码”，而是 **“写出表面能跑、测试全绿，但实际上绕过了核心约束或靠 Mock 自欺欺人的代码”** 。本文档定义：

1. 每一类功能必须在哪个层级测、用真依赖还是替身（Fake/Mock）；
2. 如何让 **Linux 无头 CI** 覆盖 85% 以上的逻辑，同时保证 **Windows 真机（Excel COM + Sandboxie + pi）**  不脱节；
3. Coding Agent 判定“我做完了”的客观门槛，以及**严禁触碰的测试作弊红线**。

### 1.2 Weft 的四大测试难点与对策

|难点|风险表现|核心对策|
| --------------------------------| ----------------------------------------------------------------| --------------------------------------------------------------------------------------|
|**Windows 独占依赖**（Excel COM、Sandboxie）|Linux CI 跑不了；真机测试慢、易受弹窗挂死|抽象 `ExcelBackend` / `Sandbox` 接口，用**同一套契约测试（Contract Tests）** 同时跑 Fake 实现与 Windows 真机实现|
|**多进程边界**（Service ↔ Workflow Worker）|Mock 掉进程通信后单元全绿，真跑时 stdio 死锁、Arrow 文件锁冲突|集成测试必须启动**真实子进程**（`.venv` + stdio JSON-RPC + Arrow IPC 文件），禁止在集成层 Mock Worker|
|**LLM 与 Agent 的非确定性**|模型输出波动导致测试偶发失败（Flaky）或 token 消耗失控|自动化测试统一打本地**剧本式 Mock LLM 服务器**（支持 SSE 流与 `tool_calls`）；真实模型仅用于录制回放与手动里程碑验收|
|**并发与状态残留**|Excel 孤儿进程、沙箱残留文件、端口占用污染下一个用例|Fixture 强隔离（每用例独立临时工作流目录 + 退出时进程/句柄泄漏断言）|

---

## 2. 测试分层与运行矩阵

标签与 `02-user-stories.md` §0.4 严格对应：

|层级标签|pytest / 工具命令|覆盖对象|外部依赖策略|运行时机与环境|单次预算|
| ----------| -----------------------| -------------------------------------------------------------------------------------------------------| ----------------------------------------------| --------------------------------------------------------------------| ------------|
| **`[unit]`** |`uv run pytest -m "not integration and not win_real"`<br />`pnpm -C frontend test`|纯函数与领域模型：DAG/Loop 折叠、端口兼容表、缓存哈希、表达式沙箱、Schema 校验与迁移、Zustand store|**零外部依赖**、零网络、零子进程|每次保存 / 每次提交；Linux + Windows CI|< 15 s|
| **`[int]`** |`uv run pytest -m integration`|Service + Engine + **真实 Worker 子进程** + FastAPI/WS + 触发器 + 打包/解包|`FakeExcelBackend` + `NoneSandbox`（影子目录）+ `MockLLMServer` + 临时文件系统|每 PR；Linux + Windows CI|< 90 s|
| **`[e2e]`** |`pnpm -C e2e test`（Playwright）|浏览器画布交互、连线校验提示、参数表单、WS 实时状态灯、Arrow 端口表格预览、聊天面板、变更审批 diff|后端以 `[int]` 相同替身模式启动真实 `weft serve`|每 PR；Linux CI（Chromium headless）|< 3 min|
| **`[int-win]`** |`uv run pytest -m win_real`<br />（封装于 `scripts/weft-test-win.ps1`）|`XlwingsBackend`（STA 线程、可见/隐藏实例、整块读写性能、弹窗繁忙重试）、`SandboxieSandbox`（`Start.exe`、写入重定向、COM 阻断）、`PiRunner`|**真实 Excel 桌面版 + 真实 Sandboxie-Plus + 真实 pi CLI**（LLM 仍可用 Mock）|M0 Spike、M3/M5 任务卡完成时、发版前；Windows 10/11 登录态桌面会话|< 5 min|
| **`[manual]`** |人工按检查单执行|真实大模型效果（场景 B/C）、Excel 视觉无闪烁体验、10 分钟从零建流体验、双机交接体验|全部真实环境 + 真实 OpenAI 兼容网关|M2–M7 里程碑出口验收|总计 ≤ 20 min|

> **关键约束**：Windows Service 或无交互桌面的 GitHub Hosted Runner 无法稳定运行桌面 Excel COM。因此 `-m win_real` 设计为在**开发者本机登录态会话**或**自托管交互式 Windows Runner** 上一键运行。

---

## 3. 契约测试（防止 Fake 与真机漂移）

任何带有 Fake 实现的子系统，**禁止为 Fake 单独写一套自说自话的测试**。必须编写参数化的契约测试基类，在 CI 跑 Fake，在真机跑真实实现：

### 3.1 `ExcelBackendContractSuite`

同一组测试用例注入 `backend fixture`（`fake` vs `xlwings`）：

1. 工作簿生命周期：`new` → `write_table` → `read_range` 往返一致（含 `Int64 / Float64 / Utf8 / Datetime / null`、`=SUM()` 公式字符串转义）。
2. `overwrite`（含 `clear_below`）与 `append` 行数、列头行为完全一致。
3. `update_cells` 地址校验：任一地址非法时，所有单元格均未发生写入（原子性前置校验）。
4. `manage_sheet`：创建、重命名、清空、删除最后一张表必报错。
5. `resolve(descriptor)`：工作簿存在时返回 `True`，关闭/不存在后返回 `False`。

### 3.2 `SandboxContractSuite`

同一组测试用例注入 `sandbox fixture`（`NoneSandbox` 影子目录 vs `SandboxieSandbox`）：

1. `read_file` 可读取真实文件；写入限定 Root/授权目录，越权路径和外网默认拒绝，真实路径内容保持不变。
2. Run 前建立内容哈希基线；`collect_changes()` 识别 created/modified/deleted，重命名仅在删除+创建内容哈希可匹配时报告 renamed，否则降级并提示。
3. 未授权目录或 `user\` 未知变化不得静默忽略，必须 `audit_complete: false`。
4. protected 路径整体拒绝且零应用；普通路径逐项返回，不要求多文件全原子。
5. apply 成功后真实文件更新，重复 apply 幂等；discard 只清未应用项。收集后修改真实目标会触发 `CHANGE_CONFLICT`，查看新 diff 并显式 overwrite 才允许继续，覆盖/删除前有备份。
6. 真机附加用例：独立 box 的创建/删除/进程归属、只终止本 Run、网络白名单有效性；这些 win_real 项不能由 NoneSandbox 结果替代。

---

## 4. 测试替身与夹具（Fixtures）规范

目录统一放在 `packages/weft/tests/fixtures/`：

### 4.1 `MockLLMServer`（内置 HTTP 桩服务）

在随机本地端口启动真实 `uvicorn` 微服务，实现 `/v1/chat/completions` 与 `/v1/models`：

- **剧本队列（Scripted Scenarios）** ：测试按顺序压入响应动作：

  - `StreamText(["分类结果：", "售后问题"])` —— 按 chunk 推送 SSE，验证 `node.stream` 事件顺序；
  - `ToolCalls([{"name": "excel_read_range", "arguments": {...}}])` —— 触发 Agent Loop 工具调用；
  - `HttpError(status=429, retry_after=0.1, times=2)` —— 验证 `LLMClient` 指数退避重试；
  - `InvalidJson("not json{")` —— 验证 `output: json` 模式的自动纠错重试（US-AGT-02/AC-2）；
  - `SlowResponse(delay=10.0)` —— 验证运行取消（Cancel）能否立即中断 HTTP 流（US-EXE-08/AC-3）。
- **请求断言**：记录每次收到的 `messages`、`tools` schema、`Authorization` 头，供断言插值与历史拼接是否正确。
- **VCR 录制回放**：支持将真实模型的响应录制为 `.cassette.json` 提交仓库，用于回归复杂 Prompt 解析。

### 4.2 标准数据夹具

- `sample_workflows/`：

  - `minimal_csv.weft`（5 节点线性流，M1 基准）
  - `branch_and_loop.weft`（含 `If`、`Merge`、`Loop Start/End`）
  - `agent_tool.weft`（含 `Agent Loop` + `Node as Tool`）
- `datasets/`：

  - `sales_utf8.csv`（1,000 行，含空值、金额、日期、中文备注）
  - `sales_gbk.csv`（验证 `encoding: auto` 自动探测 GBK）
  - `formula_injection.csv`（含 `=CMD|...` 单元格，验证写 Excel 转义）
  - `ref.xlsx`（含多 Sheet、命名区域 `MyNamed`、表格对象 `Table1`、日期格式列）

---

## 5. 各核心模块专项测试重点

### 5.1 执行引擎与缓存（`engine/`）

- **拓扑与环检测**：DAG 正常排序；普通环路必拒；成对嵌套 Loop 正确折叠；未闭合或交叉嵌套必拒；Variable 入边按显式 order 合并；动态命名端口仍遵守单入边。
- **调度终止性**：ready 中节点只出队一次；cache hit、scope skip、分支未命中都正确释放或传播到下游，最终所有节点进入终态，不死循环、不重复执行。菱形 If→A/B→Merge 分别覆盖 true、false、双侧 skipped 及与 ExecScope 相交；Merge 至少一个成功输入才执行，全部 skipped 才跳过。
- **局部执行作用域**：用计数探针验证 `to_node/from_node/single/reset` 的实际执行次数和缓存状态；`out_of_scope` 与失败后的 `skipped_upstream` 在 UI 显示 configured，只有 `skipped_branch` 显示灰色 skipped。历史端口必须读对应 Run 的内联或 outputs 文件快照。
- **缓存确定性**：参数键顺序无关；实现代码、用户代码、uv.lock、解析变量、迭代号变化均失效。显式文件输入内容变化但 mtime+size 不变仍失效；List Files 目录条目指纹变化失效；未声明参数不触发隐式文件读取；`Write CSV` 等副作用节点每次执行；LLM 与实时 Excel Read 禁止跨 Run 复用。If/Switch 缓存命中必须重放 `activated_ports`；缓存命中物化 Run 快照后，重置或 LRU 删除全局缓存不影响历史输出。
- **冻结与 CAS**：活跃 Run 使用入队时图/变量/manifest，非结构编辑不影响本 Run，NodeTool 固定参数也来自冻结快照；旧 revision 保存返回 409 且不覆盖新文档。
- **并发与取消**：两个真实 Worker 子进程执行慢节点时时间区间重叠；Run 结束后 pool 无残留，下一 Run 不继承模块全局变量或 run_id；取消只影响当前 Run。NodeTool 与正常节点共享 pool/lane 上限，池满排队，取消与 tool_timeout 能终止排队或执行中的调用。
- **队列契约**：started/queued=202、策略 drop=200 且无 run_id、队列满=409；手动/聊天/HTTP 触发行为一致。`wait=true` 被 drop 时仍直接返回 200 且无 status/outputs；等待超时返回 202、`wait_timed_out:true` 和当前 queued/running 状态，Run 不被取消。服务运行时 CLI 只走 API；服务与 CLI、两个内嵌 CLI 共用跨进程锁且不能产生两个活跃 Run，stale 锁按 PID+创建时间回收。
- **Wait 正常路径**：正常等待达到 duration_seconds 后才放行下游；取消时不放行。

### 5.2 Workflow Worker 与 IPC（`weft-worker/`）

- **环境隔离真实验证**：工作流声明主服务未安装的本地 wheel，Worker 内 import 成功、服务内失败；移除主机 PYTHONPATH 后仍能启动锁定版本的 `weft-worker`。
- **pool 契约**：单 Worker 不并发 execute，pool 默认 4 提供真实并行；进程崩溃只使当前节点失败，Run 结束所有进程退出，下一 Run 使用全新 pool。
- **Arrow IPC 文件通路**：10 万行 × 20 列只经 ValueRef 传路径与哈希，stdio 不含表格本体；分别测量序列化、写盘、哈希、memory-map 和 DataFrame 转换，不以“零拷贝”掩盖成本。

### 5.3 Excel 线程安全与异常（`excel/`）

- **STA 与串行**：非 ExcelWorker STA 线程访问 COM 立即断言；跨工作流、服务与内嵌 CLI、多个内嵌 CLI 的 COM 调用时间均不重叠。Windows 使用 `Local\WeftExcelCOM`，POSIX CI 以等价跨进程互斥实现验证同一契约。
- **多实例与实时读取**：win_real 打开多个 Excel 实例，用户按 PID/窗口选择；稳定目标存工作流，最近 PID/窗口选择只存用户级 `excel-targets.toml` 且不打包。两次 Run 间修改一个单元格，第二次必须读到新值。无人值守 Run 在已保存目标失效或匹配多个实例时必须失败，不得随机 attach 或自动切换隐藏实例。
- **超时与并发编辑**：COM 超时后本次请求失败但旧调用仍占 Worker，后续任务排队且 UI 繁忙；达到阈值或心跳失效后重建独立 ExcelWorker，排队请求以 `EXCEL_WORKER_RESTARTED` 失败，新请求恢复，写请求不自动重放，服务保持运行。用户并发编辑造成的失败须可读，不覆盖未确认内容。
- **隐藏实例归属**：仅清理 owned PID+创建时间+Run/心跳匹配的实例；fast_mode 结束恢复 ScreenUpdating；未显式选择 save/discard 不得关闭隐藏实例；Worker 恢复不得 kill 用户可见 Excel。

### 5.4 安全与边界测试（必测红线）

|编号|攻击/异常输入|预期防御行为|关联 AC|
| --------| -----------------------------------------------------------------| ----------------------------------------------------| --------------------------------|
|SEC-01|zip 含 `../../evil.dll`|拒绝解压，目标目录外零写入|US-PKG-04/AC-3|
|SEC-02|If/Polars Expression 传入 `__import__`、`__class__` 等|simpleeval 白名单/AST 白名单分别拦截，命令未执行|US-EXE-12/AC-5, US-TBL-05/AC-5|
|SEC-03|Jinja 模板遍历 `__class__.__mro__`|SandboxedEnvironment 拦截|US-AGT-09/AC-4|
|SEC-04|工作流文件含真实 api_key|打包中止并指出泄漏文件|US-SBX-08/AC-2|
|SEC-05|运行中改图，或缺少 UI 会话令牌/`X-Weft-Client: ui` 调用 PUT|运行中改图返回 409；令牌缺失/无效返回 401，缺少 header 返回 403，图结构不变；header 仅是操作标记，agent 防线依赖令牌隔离、工具白名单与 protected 文件|US-AGT-11/AC-2|
|SEC-06|apply 含 workflow.json 等 protected 路径|整体 400，无任何变更应用|US-SBX-05/AC-4|
|SEC-07|错误 Bearer token 连续 15 次|前 10 次 401，第 11 次起 429|US-SBX-09/AC-2|
|SEC-08|NodeTool 指向 Python/Shell/未声明节点或暴露非白名单参数|保存和直接调用均拒绝，无法借可信 lane 绕过沙箱|US-AGT-04/AC-1,2,7|
|SEC-09|pi/沙箱尝试读取原始 key、直连外网/其他主机服务，或写未授权目录|env/stdout/trace 无 key，外网与越权写默认拒绝；仅指定环回 LLMProxy 可访问且代理只允许配置端点|US-AGT-06/AC-4, US-SBX-03/AC-4|
|SEC-10|收集后真实目标被用户修改，再 apply|批量请求返回 200，该项 status=conflict、error.code=CHANGE_CONFLICT且不覆盖；查看新 diff 并显式确认后才可覆盖|US-SBX-05/AC-1,2|
|SEC-11|沙箱产生重命名或未知 `user\` 变更|哈希可判定才报 renamed；否则删除+创建并提示；未知变更使 audit_complete=false|US-SBX-04/AC-1,2,4|
|SEC-12|伪造 Host/Origin、未认证 WS 订阅，或复用缺失/错误的 UI 会话令牌|Host/Origin 失败返回 403；WS 不推送；API 返回 401/403；令牌不出现在日志/trace|US-SBX-09/AC-4,5|
|SEC-13|在 NoneSandbox 请求 bash/pi 或直接主机 spawn|运行前拒绝，只开放受控影子目录文件工具|US-AGT-05/AC-4, US-AGT-06/AC-6, US-SBX-01/AC-2|

---

## 6. 性能基准测试（Performance Benchmarks）

使用 `pytest-benchmark`（`@pytest.mark.benchmark`）先建立基线，再在同机回归。报告必须记录 CPU、RAM、OS、Excel/Python/依赖版本、数据类型、冷/热缓存及是否包含序列化/哈希；PRD 数值是受控目标，不是任意机器的通用 CI 硬门槛。

|基准项|测量方法|受控目标|运行环境|
| -------------------| -----------------------------------------------------------------| ------------------------------| --------------|
|引擎纯调度|50 个 No-op 线性节点，扣除固定开销|< 5 ms / 节点|固定 Linux/Win 基准机|
|Arrow 跨 Worker|100,000 行 × 20 列 IPC 往返，分别报告序列化、写盘、哈希、映射、转换|< 100 ms|固定 Linux/Win 基准机|
|缓存命中物化 Run 快照|复用 100,000 行 × 20 列 pure 缓存，复制到本 Run outputs 并复用已有哈希；分别报告复制耗时与磁盘增量|M0/M1 建基线，同机回归|固定 Linux/Win 基准机|
|Excel 整块读取|1000 × 100 整块读取为 Arrow 表|< 3.0 s|固定 win_real 基准机|
|Excel 整块写入|1000 × 100 整块写入；另比较逐格与批量合并调用|< 3.0 s|固定 win_real 基准机|
|WS 状态推送|状态变更到 WS 客户端收到帧，p95|< 200 ms|固定 CI 基准环境|
|服务冷启动|启动到 version 200；首屏可交互单独测量|< 2.0 s / 5.0 s|固定 E2E 基准环境|

基准结果与环境不符时只记录不阻断普通 PR；同一基准机出现显著回归才阻断。Excel 指标只能由 win_real 验证，Fake/Linux 绿灯不能替代。

2026-11-04 本机 Arrow 100,000×20 冷缓存基准由 `packages/weft/tests/test_performance.py` 产出，三次总耗时分别为 24.065、24.012、24.194 ms，均低于 100 ms。序列化、写盘、SHA-256、memory-map 和 Polars 转换的分阶段结果及 CPU/RAM/依赖版本保存在 `.test-reports/arrow-worker-benchmark-run1.json` 至 `run3.json`。

同一文件还记录 50 个线性 No-op 节点和 50 次认证 WS 推送。三次引擎调度分别为 1.600、1.646、1.592 ms/节点，均低于 5 ms；WS p95 分别为 0.206、0.249、0.217 ms，均低于 200 ms。对应报告为 `.test-reports/engine-scheduler-benchmark-run*.json` 与 `ws-latency-benchmark-run*.json`。

真实 `weft serve` 冷启动到健康检查和鉴权 version 均可用，三次分别为 0.821、0.785、0.663 秒，均低于 2 秒；报告为 `.test-reports/service-cold-start-benchmark-run*.json`。首屏可交互时间仍由 E2E 单独验收，不与该值混为一谈。

100,000×20 pure 缓存命中物化通过 `CacheManager.store → load → materialize` 验证，三次复制分别为 6.483、5.525、6.363 ms；每次磁盘增量均为 16,003,194 字节，与源 Arrow 文件一致，哈希保持复用。报告为 `.test-reports/cache-materialize-benchmark-run*.json`，作为后续同机回归基线。

---

## 7. AC 追溯矩阵与自动化覆盖门禁

### 7.1 绑定约定

每个验证用户故事验收标准的测试函数（Python `pytest` 或 TS `Playwright`/`Vitest`），必须在 docstring 或测试标题中显式标注 `US-XXX-NN/AC-M`（可标注多个）：

```python
def test_reject_incompatible_table_to_excel_edge():
    """US-DES-03/AC-2, US-DES-03/AC-5: Table port cannot connect to Excel port."""
    assert not is_compatible(PortType.TABLE, PortType.EXCEL)
```

```ts
test('US-DES-05/AC-1: renders red/yellow/green status bar on canvas nodes', async ({ page }) => {
  // ...
});
```

### 7.2 `scripts/coverage_matrix.py` 门禁逻辑

仓库内置检查脚本，纳入 `uv run poe check`：

1. 解析 `docs/02-user-stories.md` 的全部 US/AC，建立合法引用集合并区分 `[manual]`；
2. 解析 `docs/07-roadmap.md` 的任务卡，格式必须为 `- [ ] **T…**` 或 `- [x] **T…**`，只有 `[x]` 是完成；任何不存在的 US/AC 引用都立即报错；
3. 扫描 `packages/**/tests/`、`frontend/src/**/*.test.*`、`e2e/` 中的 US/AC 标记，未知标记同样报错；
4. 仅对 `[x]` 已完成卡，检查其声明的所有非 manual AC 至少有一个对应测试；缺失则退出 1。manual AC 必须出现在人工验收单，不能要求自动化函数冒充；
5. 所有任务默认未完成，文档编写或任务卡文字调整不得自动改为 `[x]`。Fake/Linux 结果只能覆盖其声明环境，涉及 win_real 的完成卡还必须记录真机结果。

### 7.3 代码覆盖率指标

- 只作为发现死代码与漏测分支的辅助指标，不替代 AC 覆盖：

  - `weft/engine/`、`weft/workflow/`、`weft/agent/`：**行覆盖率 ≥ 85%**
  - `weft/nodes/`、`weft/triggers/`、`weft/sandbox/`：**行覆盖率 ≥ 75%**
  - `weft/excel/xlwings_backend.py`（仅在 `win_real` 统计）： **≥ 70%**

---

## 8. Coding Agent 测试反作弊红线（硬性规定）

在让 AI Agent 自动写代码和修测试时，以下行为视为**任务失败，直接打回**：

1. **禁止删除、跳过或弱化失败测试**：不得擅自添加 `@pytest.mark.skip`、`xfail`、`test.skip`，不得为了凑绿把断言改成 `assert result is not None` 或 `assert True`。
2. **禁止在集成测试中 Mock 被测系统内部模块**：`[int]` 测试只允许替换外部系统边界（Excel、Sandboxie、远端 LLM API），**严禁** `monkeypatch` 掉 `WorkflowWorker`、`CacheManager`、JSON-RPC 通道或文件读写。
3. **禁止在生产代码中写测试特判分支**：严禁出现 `if os.getenv("PYTEST_CURRENT_TEST"): return fake_data`（仅允许线程安全断言等更严格的 debug 检查）。
4. **禁止无断言测试**：每个测试函数必须有验证业务结果的显式 `assert` / `expect`（不能只调一遍函数不抛异常就算测过）。
5. **先写失败测试（Red → Green）** ：修复 Bug 或实现 AC 时，优先先写出对应 `US-XXX-NN/AC-M` 的失败测试，再写实现使其变绿。
6. **真机测试未跑必须如实声明**：Agent 在无 Excel/Sandboxie 的环境中开发时，只能跑通 Fake 契约测试，必须在交付说明中列出待人类在 Windows 真机执行的 `win_real` 命令清单，不得宣称真机已验证。

---

## 9. CI 流水线与发布验收流程

### 9.1 GitHub Actions（每 PR 自动触发）

```yaml
jobs:
  lint-and-type:       # ruff + mypy (linux & win32 target) + import-linter + eslint + tsc
  unit-and-int-linux:  # ubuntu-latest: uv run pytest (unit + integration) + coverage_matrix.py
  unit-and-int-win:    # windows-latest: uv run pytest (unit + integration, 验证 Windows 路径/分隔符/CTRL_BREAK 信号)
  frontend-and-e2e:    # ubuntu-latest: vitest + playwright (启动真实后端 + Fake backends)
```

### 9.2 Windows 真机一键回归脚本（`scripts/weft-test-win.ps1`）

供你在本地 Windows 终端在里程碑节点运行：

1. 前置运行 `uv run weft doctor`（Excel 实例列表、动态 Sandboxie box、网络默认拒绝、uv 就绪）；
2. 记录当前 `EXCEL.EXE` PID+创建时间与 Weft owned 实例/box 登记，避免误杀用户工作簿或其他 Run；
3. 运行 `uv run pytest -m "win_real or benchmark" -v`，性能报告包含基准环境与分阶段耗时；
4. 检查 owned 隐藏 Excel 与本 Run box 无残留，只能按登记匹配清理，不匹配则报告人工处理；
5. 输出 `.test-reports/win-real-<timestamp>.xml`；任何 win_real 未运行/失败都明确标为未验证，不能用 Fake 结果补齐。

### 9.3 里程碑手动验收单（`[manual]`）

每个里程碑结束前，由作者本人执行对应的手动检查（总计不超过 20 分钟）：

- **M2**：计时从空白新建工作流，拖入 CSV 读 → 筛选 → 聚合 → CSV 写，预览中间表并跑通，确认 ≤ 10 分钟且无需翻源码。
- **M3**：打开自己日常用的一份真实 `.xlsx`，放在副屏看着，运行工作流写入新 Sheet 并更新几个汇总单元格，确认无闪烁、不抢焦点、格式不丢。
- **M4**：接入真实 NewAPI 模型端点，跑场景 B（50 条真实备注分类），抽查 10 条分类质量与轨迹时间线可读性。
- **M5**：在真实 Sandboxie 下跑 `Pi Agent` 整理测试目录，确认审批前真实目录纹丝不动、审批勾选部分文件后精确落地。
- **M6**：`weft pack` 产出一个 `.weft.zip`，拷到另一目录（或同事电脑）`weft unpack` + `weft run` 一次跑通；双方主服务与 Worker 必须精确同版本，版本不同应先看到明确的升级/重锁提示，而不是被当成运行 bug。
