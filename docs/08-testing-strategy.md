# 08-testing-strategy.md

# Weft 测试策略

|项|值|
| ------| -----------------------------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`01-prd.md`​（§9.3 性能目标）、​`02-user-stories.md`​（AC 真源）、​`03-architecture.md`​、​`06-engineering.md`|
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
|**Windows 独占依赖**（Excel COM、Sandboxie）|Linux CI 跑不了；真机测试慢、易受弹窗挂死|抽象 ​`ExcelBackend`​ / ​`Sandbox`​ 接口，用**同一套契约测试（Contract Tests）** 同时跑 Fake 实现与 Windows 真机实现|
|**多进程边界**（Service ↔ Workflow Worker）|Mock 掉进程通信后单元全绿，真跑时 stdio 死锁、Arrow 文件锁冲突|集成测试必须启动**真实子进程**（​`.venv` + stdio JSON-RPC + Arrow IPC 文件），禁止在集成层 Mock Worker|
|**LLM 与 Agent 的非确定性**|模型输出波动导致测试偶发失败（Flaky）或 token 消耗失控|自动化测试统一打本地**剧本式 Mock LLM 服务器**（支持 SSE 流与 ​`tool_calls`）；真实模型仅用于录制回放与手动里程碑验收|
|**并发与状态残留**|Excel 孤儿进程、沙箱残留文件、端口占用污染下一个用例|Fixture 强隔离（每用例独立临时工作流目录 + 退出时进程/句柄泄漏断言）|

---

## 2. 测试分层与运行矩阵

标签与 ​`02-user-stories.md` §0.4 严格对应：

|层级标签|pytest / 工具命令|覆盖对象|外部依赖策略|运行时机与环境|单次预算|
| ----------| -----------------------| -------------------------------------------------------------------------------------------------------| ----------------------------------------------| --------------------------------------------------------------------| ------------|
| **​`[unit]`​** |`uv run pytest -m "not integration and not win_real"`<br />​`pnpm -C frontend test`|纯函数与领域模型：DAG/Loop 折叠、端口兼容表、缓存哈希、表达式沙箱、Schema 校验与迁移、Zustand store|**零外部依赖**、零网络、零子进程|每次保存 / 每次提交；Linux + Windows CI|< 15 s|
| **​`[int]`​** |`uv run pytest -m integration`|Service + Engine + **真实 Worker 子进程** + FastAPI/WS + 触发器 + 打包/解包|`FakeExcelBackend`​ + ​`NoneSandbox`​（影子目录）+ ​`MockLLMServer` + 临时文件系统|每 PR；Linux + Windows CI|< 90 s|
| **​`[e2e]`​** |`pnpm -C e2e test`（Playwright）|浏览器画布交互、连线校验提示、参数表单、WS 实时状态灯、Arrow 端口表格预览、聊天面板、变更审批 diff|后端以 ​`[int]`​ 相同替身模式启动真实 ​`weft serve`|每 PR；Linux CI（Chromium headless）|< 3 min|
| **​`[int-win]`​** |`uv run pytest -m win_real`<br />（封装于 ​`scripts/weft-test-win.ps1`）|`XlwingsBackend`​（STA 线程、可见/隐藏实例、整块读写性能、弹窗繁忙重试）、​`SandboxieSandbox`​（​`Start.exe`​、写入重定向、COM 阻断）、​`PiRunner`|**真实 Excel 桌面版 + 真实 Sandboxie-Plus + 真实 pi CLI**（LLM 仍可用 Mock）|M0 Spike、M3/M5 任务卡完成时、发版前；Windows 10/11 登录态桌面会话|< 5 min|
| **​`[manual]`​** |人工按检查单执行|真实大模型效果（场景 B/C）、Excel 视觉无闪烁体验、10 分钟从零建流体验、双机交接体验|全部真实环境 + 真实 OpenAI 兼容网关|M2–M7 里程碑出口验收|15–30 min|

> **关键约束**：Windows Service 或无交互桌面的 GitHub Hosted Runner 无法稳定运行桌面 Excel COM。因此 ​`-m win_real`​ 设计为在**开发者本机登录态会话**或**自托管交互式 Windows Runner** 上一键运行。

---

## 3. 契约测试（防止 Fake 与真机漂移）

任何带有 Fake 实现的子系统，**禁止为 Fake 单独写一套自说自话的测试**。必须编写参数化的契约测试基类，在 CI 跑 Fake，在真机跑真实实现：

### 3.1 ​`ExcelBackendContractSuite`

同一组测试用例注入 ​`backend fixture`​（​`fake`​ vs ​`xlwings`）：

1. 工作簿生命周期：​`new`​ → ​`write_table`​ → ​`read_range`​ 往返一致（含 ​`Int64 / Float64 / Utf8 / Datetime / null`​、​`=SUM()` 公式字符串转义）。
2. `overwrite`​（含 ​`clear_below`​）与 ​`append` 行数、列头行为完全一致。
3. `update_cells` 地址校验：任一地址非法时，所有单元格均未发生写入（原子性前置校验）。
4. `manage_sheet`：创建、重命名、清空、删除最后一张表必报错。
5. `resolve(descriptor)`​：工作簿存在时返回 ​`True`​，关闭/不存在后返回 ​`False`。

### 3.2 ​`SandboxContractSuite`

同一组测试用例注入 ​`sandbox fixture`​（​`NoneSandbox`​ 影子目录 vs ​`SandboxieSandbox`）：

1. `read_file` 可读取工作流 Root 内外已存在的真实文件。
2. `write_file`​ 与子进程写出文件后，**真实路径内容保持不变**。
3. `collect_changes()`​ 准确识别 ​`created`​、​`modified`​、​`deleted`​ 三种状态及文件大小、​`is_text`。
4. 受保护路径（​`workflow.json`​、​`pyproject.toml`​、​`uv.lock`​、​`.runs/**`​、​`config.toml`​）一律标记 ​`protected: true`​，调用 ​`apply()` 包含任一受保护路径时整体拒绝且不产生部分写入。
5. `apply()`​ 成功后真实文件更新，再次调用 ​`apply()`​ 幂等返回已应用；​`discard()` 后变更清空且真实文件未动。

---

## 4. 测试替身与夹具（Fixtures）规范

目录统一放在 ​`packages/weft/tests/fixtures/`：

### 4.1 ​`MockLLMServer`（内置 HTTP 桩服务）

在随机本地端口启动真实 ​`uvicorn`​ 微服务，实现 ​`/v1/chat/completions`​ 与 ​`/v1/models`：

- **剧本队列（Scripted Scenarios）** ：测试按顺序压入响应动作：

  - `StreamText(["分类结果：", "售后问题"])`​ —— 按 chunk 推送 SSE，验证 ​`node.stream` 事件顺序；
  - `ToolCalls([{"name": "excel_read_range", "arguments": {...}}])` —— 触发 Agent Loop 工具调用；
  - `HttpError(status=429, retry_after=0.1, times=2)`​ —— 验证 ​`LLMClient` 指数退避重试；
  - `InvalidJson("not json{")`​ —— 验证 ​`output: json` 模式的自动纠错重试（US-AGT-02/AC-2）；
  - `SlowResponse(delay=10.0)` —— 验证运行取消（Cancel）能否立即中断 HTTP 流（US-EXE-08/AC-3）。
- **请求断言**：记录每次收到的 ​`messages`​、​`tools`​ schema、​`Authorization` 头，供断言插值与历史拼接是否正确。
- **VCR 录制回放**：支持将真实模型的响应录制为 ​`.cassette.json` 提交仓库，用于回归复杂 Prompt 解析。

### 4.2 标准数据夹具

- `sample_workflows/`：

  - `minimal_csv.weft`（5 节点线性流，M1 基准）
  - `branch_and_loop.weft`​（含 ​`If`​、​`Merge`​、​`Loop Start/End`）
  - `agent_tool.weft`​（含 ​`Agent Loop`​ + ​`Node as Tool`）
- `datasets/`：

  - `sales_utf8.csv`（1,000 行，含空值、金额、日期、中文备注）
  - `sales_gbk.csv`​（验证 ​`encoding: auto` 自动探测 GBK）
  - `formula_injection.csv`​（含 ​`=CMD|...` 单元格，验证写 Excel 转义）
  - `ref.xlsx`​（含多 Sheet、命名区域 ​`MyNamed`​、表格对象 ​`Table1`、日期格式列）

---

## 5. 各核心模块专项测试重点

### 5.1 执行引擎与缓存（​`engine/`）

- **拓扑与环检测**：DAG 正常排序；普通环路必拒；成对嵌套的 ​`Loop Start/End` 正确折叠；未闭合或交叉嵌套的 Loop 必拒。
- **局部执行作用域（ExecScope）** ：构造带计数器的探针节点（记录实际执行次数），严格验证 ​`to_node`​、​`from_node`​、​`single`​、​`reset` 下每个节点的执行次数与缓存命中状态。
- **缓存确定性**：参数字典键顺序打乱、无关空白变化，缓存键不变；上游输入文件 ​`mtime`​ 或 ​`size`​ 变化、节点 ​`node_version` 升级、流变量解析值变化，缓存必失效。
- **并发与取消**：两个无依赖慢节点（各 sleep 0.3s）总耗时 < 0.45s（证明真并行）；执行 0.1s 后触发 ​`cancel`​，Run 在 2s 内进入 ​`cancelled`，Worker 子进程无残留，已完成节点的缓存仍有效。

### 5.2 Workflow Worker 与 IPC（​`worker/`）

- **环境隔离真实验证**：测试工作流声明一个 Weft 本体未安装的轻量纯 Python 小包（或本地 wheel 夹具），验证 Worker 内 ​`import`​ 成功而服务进程内 ​`import` 失败。
- **崩溃恢复**：构造一个执行 ​`os._exit(137)`​（模拟段错误/OOM 被杀）的恶意节点，验证服务进程不崩溃、该节点状态变为 ​`failed` 并附清晰错误、下一次 Run 能自动拉起新 Worker。
- **大数据零拷贝通路**：传递 10 万行 × 20 列 Arrow 表，验证 JSON-RPC stdout 行内不包含表格数据本体（单行长度 < 4 KB），只传 ​`ValueRef` 路径与哈希。

### 5.3 Excel 线程安全与异常（​`excel/`）

- **STA 线程断言**：在 debug/test 模式下，任何非 ​`ExcelWorker`​ 线程直接访问底层 COM 包装对象立即抛 ​`AssertionError`（US-XLS-11/AC-1）。
- **跨工作流串行**：同时启动 2 个均含 Excel 读写的工作流，注入延迟，验证调用时间区间严格不重叠且无 ​`RPC_E_WRONG_THREAD`。
- **模态框阻塞模拟**：通过桩模拟 COM 抛出 ​`0x800AC472`​（​`VBA_E_IGNORE`​ / ​`RPC_E_CALL_REJECTED`​），验证重试 3 次后返回可读的 ​`ExcelBusyError`，而非无限挂起。
- **隐藏实例零泄漏**：​`win_real`​ 测试前后快照系统 ​`EXCEL.EXE`​ PID 集合，测试结束后不得多出任何新增的隐藏 ​`EXCEL.EXE` 进程。

### 5.4 安全与边界测试（必测红线）

|编号|攻击/异常输入|预期防御行为|关联 AC|
| --------| -----------------------------------------------------------------| ----------------------------------------------------| --------------------------------|
|SEC-01|`weft unpack`​ 导入含 ​`../../evil.dll` 条目的构造 zip|拒绝解压，返回 400，目标目录外零文件写入|US-PKG-04/AC-3|
|SEC-02|`If`​ 条件或 ​`Polars Expression`​ 传入 ​`__import__('os').system('calc')`​ 或 ​`().__class__.__base__`|AST/沙箱拦截，节点失败且命令未执行|US-EXE-12/AC-5, US-TBL-05/AC-5|
|SEC-03|`Prompt Template`​ 传入 ​`{{ ''.__class__.__mro__ }}`|Jinja2 ​`SandboxedEnvironment`​ 拦截 ​`SecurityError`|US-AGT-09/AC-4|
|SEC-04|工作流目录下某文本文件混入 ​`config.toml`​ 中的真实 ​`api_key`​ 明文，执行 ​`weft pack`|全文扫描命中，打包中止并指出泄漏文件名，不生成 zip|US-SBX-08/AC-2|
|SEC-05|Run 处于 ​`running`​ 状态，或请求不带 ​`X-Weft-Client: ui`​ 头，调用 ​`PUT /api/workflows/{id}` 修改节点/连线|返回 409 / 403，图结构不变（防 Agent 自改图）|US-AGT-11/AC-2|
|SEC-06|沙箱内进程修改了 ​`workflow.json`​，调用 ​`POST /changes/apply` 传入该路径|返回 400，全部变更不应用|US-SBX-05/AC-4|
|SEC-07|未带或带错 Bearer token 调用 ​`POST /trigger` 连续 15 次|前 10 次返回 401，第 11 次起返回 429 限流|US-SBX-09/AC-2|

---

## 6. 性能基准测试（Performance Benchmarks）

使用 ​`pytest-benchmark`​（标记 ​`@pytest.mark.benchmark`，归入集成/真机门禁），硬性对齐 PRD §9.3：

|基准项|测量方法|通过阈值|运行环境|
| -------------------| -----------------------------------------------------------------| ------------------------------| --------------|
|引擎纯调度开销|50 个空操作（No-op）节点线性串联执行，扣除首尾固定开销后除以 50| **&lt; 5 ms / 节点**|Linux/Win CI|
|节点间 Arrow 传递|100,000 行 × 20 列（混合数值/字符串）经 Worker IPC 往返一次| **&lt; 100 ms**|Linux/Win CI|
|Excel 整块读取|`Excel Read Range`​ 读取 ​`1000 × 100`（10 万单元格）为 Arrow 表| **&lt; 3.0 s**|`win_real`|
|Excel 整块写入|`Excel Write Table`​ 将 ​`1000 × 100`​ 表写入可见实例（​`fast_mode=True`）| **&lt; 3.0 s**|`win_real`|
|WS 状态推送延迟|节点状态变更时刻到测试 WS 客户端收到 ​`node.status` 帧的耗时（p95）| **&lt; 200 ms**|Linux/Win CI|
|服务冷启动|子进程启动 ​`weft serve --no-browser`​ 到 ​`GET /api/system/version` 返回 200| **&lt; 2.0 s**（含前端首屏可交互 < 5.0 s）|E2E CI|

---

## 7. AC 追溯矩阵与自动化覆盖门禁

### 7.1 绑定约定

每个验证用户故事验收标准的测试函数（Python ​`pytest`​ 或 TS ​`Playwright`​/​`Vitest`​），必须在 docstring 或测试标题中显式标注 ​`US-XXX-NN/AC-M`（可标注多个）：

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

### 7.2 ​`scripts/coverage_matrix.py` 门禁逻辑

仓库内置检查脚本，纳入 ​`uv run poe check`：

1. 解析 ​`docs/02-user-stories.md`​ 中所有非 ​`[manual]` 的 AC 条目；
2. 解析 ​`docs/07-roadmap.md` 中已标记完成的任务卡所声明的【验收】AC 集合；
3. 扫描 ​`packages/**/tests/`​、​`frontend/src/**/*.test.*`​、​`e2e/`​ 中的 ​`US-XXX-NN/AC-M` 标记；
4. **若已完成任务卡名下的任一自动化 AC 找不到对应测试函数，脚本退出码为 1，CI 直接失败。**

### 7.3 代码覆盖率指标

- 只作为发现死代码与漏测分支的辅助指标，不替代 AC 覆盖：

  - `weft/engine/`​、​`weft/workflow/`​、​`weft/agent/`​：**行覆盖率 ≥ 85%**
  - `weft/nodes/`​、​`weft/triggers/`​、​`weft/sandbox/`​：**行覆盖率 ≥ 75%**
  - `weft/excel/xlwings_backend.py`​（仅在 ​`win_real`​ 统计）： **≥ 70%**

---

## 8. Coding Agent 测试反作弊红线（硬性规定）

在让 AI Agent 自动写代码和修测试时，以下行为视为**任务失败，直接打回**：

1. **禁止删除、跳过或弱化失败测试**：不得擅自添加 ​`@pytest.mark.skip`​、​`xfail`​、​`test.skip`​，不得为了凑绿把断言改成 ​`assert result is not None`​ 或 ​`assert True`。
2. **禁止在集成测试中 Mock 被测系统内部模块**：​`[int]`​ 测试只允许替换外部系统边界（Excel、Sandboxie、远端 LLM API），**严禁** ​`monkeypatch`​ 掉 ​`WorkflowWorker`​、​`CacheManager`、JSON-RPC 通道或文件读写。
3. **禁止在生产代码中写测试特判分支**：严禁出现 ​`if os.getenv("PYTEST_CURRENT_TEST"): return fake_data`（仅允许线程安全断言等更严格的 debug 检查）。
4. **禁止无断言测试**：每个测试函数必须有验证业务结果的显式 ​`assert`​ / ​`expect`（不能只调一遍函数不抛异常就算测过）。
5. **先写失败测试（Red → Green）** ：修复 Bug 或实现 AC 时，优先先写出对应 ​`US-XXX-NN/AC-M` 的失败测试，再写实现使其变绿。
6. **真机测试未跑必须如实声明**：Agent 在无 Excel/Sandboxie 的环境中开发时，只能跑通 Fake 契约测试，必须在交付说明中列出待人类在 Windows 真机执行的 ​`win_real` 命令清单，不得宣称真机已验证。

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

### 9.2 Windows 真机一键回归脚本（​`scripts/weft-test-win.ps1`）

供你在本地 Windows 终端在里程碑节点运行：

1. 前置运行 ​`uv run weft doctor`​（确认 Excel、Sandboxie ​`WeftBox`、uv 就绪）；
2. 记录当前用户的 ​`EXCEL.EXE` 进程列表（确保不误杀你已经打开的工作簿）；
3. 运行 ​`uv run pytest -m "win_real or benchmark" -v`；
4. 检查是否有残留隐藏 ​`EXCEL.EXE`​ 或 ​`WeftBox` 残留进程，若有则报错提示；
5. 输出测试报告至 ​`.test-reports/win-real-<timestamp>.xml`。

### 9.3 里程碑手动验收单（​`[manual]`）

每个里程碑结束前，由作者本人执行对应的手动检查（总计不超过 20 分钟）：

- **M2**：计时从空白新建工作流，拖入 CSV 读 → 筛选 → 聚合 → CSV 写，预览中间表并跑通，确认 ≤ 10 分钟且无需翻源码。
- **M3**：打开自己日常用的一份真实 ​`.xlsx`，放在副屏看着，运行工作流写入新 Sheet 并更新几个汇总单元格，确认无闪烁、不抢焦点、格式不丢。
- **M4**：接入真实 NewAPI 模型端点，跑场景 B（50 条真实备注分类），抽查 10 条分类质量与轨迹时间线可读性。
- **M5**：在真实 Sandboxie 下跑 ​`Pi Agent` 整理测试目录，确认审批前真实目录纹丝不动、审批勾选部分文件后精确落地。
- **M6**：​`weft pack`​ 产出一个 ​`.weft.zip`​，拷到另一目录（或同事电脑）​`weft unpack`​ + ​`weft run` 一次跑通。

‍
