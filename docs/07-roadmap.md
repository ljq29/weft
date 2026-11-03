# 07-roadmap.md

# **Weft 路线图与任务拆解**

|项|值|
| ------| ---------------------------------------------------------------------------------|
|版本|v0.1（草稿）|
|上游|`01-prd.md`​ §7 优先级、​`02-user-stories.md`|
|用法|agent 按任务卡顺序领取；每张卡独立可验证，完成 = 列出的 AC 测试通过 + ​`poe check` 全绿|

---

## 0. 里程碑总览

|里程碑|主题|出口标准（Demo）|
| --------| ---------------------| ------------------------------------------------------------|
|**M0**|骨架与风险验证|仓库可构建；三个技术 spike 有结论|
|**M1**|引擎核心 + 最小闭环|CLI 跑通 ​`Trigger → Read CSV → Row Filter → Write CSV`，含缓存与局部执行|
|**M2**|画布 UI|浏览器中设计并运行 M1 工作流，状态实时、端口可预览|
|**M3**|Excel 联动|场景 A（读打开的 Excel → 处理 → 写回打开的 Excel）端到端|
|**M4**|Agent|场景 B（Agent Loop + Node as Tool）端到端|
|**M5**|沙箱|场景 C（Pi/沙箱工具 + 变更审批）端到端|
|**M6**|触发器 + 打包|场景 D、E 端到端；​`pack → unpack → run` 跨目录通过|
|**M7**|收尾|P1 项、运行历史、doctor、文档、​`0.1.0` 发布|

依赖关系：M1 → M2 → M3 → M4 → M5 → M6 → M7 线性为主；M3 与 M2 可部分并行（Excel 子系统不依赖 UI）。

规则：

- 每张卡标注【依赖】【产出】【验收】；验收引用 ​`02-user-stories.md` 的 AC。
- P2/占位项不排卡。P1 项集中在 M7，若时间紧可砍。
- 实现中发现文档缺口：小缺口在 PR 中补文档；大缺口（影响数据模型/API）先停下来改文档再继续。

---

## M0 骨架与风险验证

> 目标：把"后面会死人的坑"先踩掉。spike 代码允许丢弃，结论必须写回文档。

**T0.1 仓库骨架**  
【依赖】无  
【产出】monorepo 目录（​`06-engineering.md`​ §1）；uv workspace；​`weft`​ / ​`weft-sdk`​ 空包可安装；frontend Vite 骨架；ruff/mypy/eslint/pytest/vitest/poe check 全部就绪；CI（Linux + Windows）跑通空测试；import-linter 分层规则生效  
【验收】​`uv run poe check` 与两平台 CI 绿

**T0.2 Spike：Sandboxie 变更收集**（最高风险，​`03-architecture.md`​ §12）  
【依赖】T0.1  
【产出】Windows 真机验证脚本 + 结论写入 ​`03-architecture.md`​ §7.2：​`Start.exe`​ 启动/等待/终止、stdout 回传方案、​`drive\` 目录结构、删除标记的实际形态、网络可用性  
【验收】脚本演示 created/modified/deleted 三种变更被正确收集；若发现方案不可行，提出替代并更新文档（此时停止后续沙箱卡）

**T0.3 Spike：xlwings attach 行为**  
【依赖】T0.1  
【产出】真机验证：GetActiveObject 多实例行为、已打开工作簿写回可见性、​`RPC_E_CALL_REJECTED`​ 重现与重试、10 万单元格整块读写耗时；结论写入 ​`03-architecture.md`​ §5  
【验收】​`docs/spikes/excel.md` 记录数据；性能达标或调整 PRD §9.3 指标

**T0.4 Spike：pi 非交互模式**  
【依赖】T0.1  
【产出】确认 pi 的非交互调用方式、输出格式、API key 注入、退出码；固定命令行写入 ​`06-nodes-v1.md`（Pi Agent 节点）  
【验收】脚本演示给定 task 运行 pi 并解析输出

---

## M1 引擎核心 + 最小闭环

**T1.1 数据模型与校验**  
【依赖】T0.1  
【产出】​`weft.workflow`​：Pydantic 模型（workflow.json 全量，​`04-data-model.md` §2）、校验规则表、原子保存、迁移框架骨架  
【验收】US-PKG-05/AC-1,2；US-DES-07/AC-4；校验规则表全部有测试

**T1.2 端口类型与 ValueRef**  
【依赖】T1.1  
【产出】​`PortType`​ 枚举、兼容矩阵、​`ValueRef` 序列化/反序列化、缓存键计算（canonical JSON + 哈希）  
【验收】US-DES-03/AC-5（36 组合测试表）；US-EXE-04/AC-1

**T1.3 节点协议与注册表**  
【依赖】T1.2  
【产出】​`weft-sdk`​：​`Node`​ 基类、​`Port`​、​`@weft.node`​、​`weft_ctx`​；​`weft`​：内置注册表 + 用户 ​`nodes/` 扫描  
【验收】示例自定义节点可注册、schema 可导出（US-DES-04/AC-4）

**T1.4 调度器与 Run 状态机**  
【依赖】T1.3  
【产出】​`weft.engine`：拓扑排序、ExecScope、并行执行、分支 skip、失败传播、取消、Run 队列与并发策略  
【验收】US-EXE-01/AC-1,2,3；US-EXE-02；US-EXE-03；US-EXE-08/AC-1,4；US-EXE-12/AC-1,2,3；US-EXE-13/AC-1,2（全部用内存测试节点，无 Worker）

**T1.5 缓存层**  
【依赖】T1.4  
【产出】缓存读写、命中判定、失效、LRU 清理、打开工作流时恢复状态  
【验收】US-EXE-04/AC-2,3,4,5

**T1.6 Workflow Worker 与 IPC**  
【依赖】T1.4  
【产出】JSON-RPC over stdio、Arrow 文件传值、Worker 生命周期（启动/保活/依赖变更重启/取消/崩溃重启）、​`uv sync` 集成  
【验收】US-EXE-14/AC-1..5；US-EXE-08/AC-2；A-01/A-03 行为有集成测试

**T1.7 基础表格与文件节点（第一批）**   
【依赖】T1.6  
【产出】​`Read/Write CSV·Parquet·JSON`​、​`Column Filter`​、​`Row Filter`​、​`Sorter`​、​`Column Rename`​、​`Variable`​、​`Table Row Count`​、​`List Files`  
【验收】US-TBL-02/AC-1,3,4,5；US-TBL-03/AC-1..4,8；US-TBL-06/AC-3,4；US-TBL-07/AC-1

**T1.8 流程节点（第一批）与 CLI run**  
【依赖】T1.7  
【产出】​`Trigger`​（仅 manual）、​`If`​、​`Switch`​、​`Merge`​、​`Wait`​；​`weft run`​（内嵌模式）、​`weft serve`​ 最小 API（workflows CRUD + runs）  
【验收】US-TRG-01/AC-1；US-TRG-02/AC-2；**里程碑 Demo**：​`weft run demo.weft`​ 跑通 CSV 闭环，二次运行全缓存命中，​`--var` 覆盖生效

---

## M2 画布 UI

**T2.1 REST/WS 完整化**  
【依赖】T1.8  
【产出】​`05-api.md` §1–5、§11 中 M2 所需端点与事件；WS 多路订阅；错误码统一  
【验收】API 集成测试覆盖每个端点的 200 与主要错误路径

**T2.2 画布编辑**  
【依赖】T2.1  
【产出】React Flow 画布：节点面板、拖拽、连线（后端校验）、参数表单（JSON Schema 生成）、变量绑定控件、自动保存、undo/redo、复制粘贴、导航、小地图  
【验收】US-DES-01..04、US-DES-06..08、US-DES-11 的全部 AC（e2e 用 Playwright）

**T2.3 执行可视化**  
【依赖】T2.2  
【产出】状态灯、右键执行菜单（到此/从此/仅此/重置）、日志面板、端口视图（Arrow 流直读 + 分页排序）、错误详情  
【验收】US-DES-05；US-EXE-05/AC-1,3,4；US-EXE-06/AC-1,3,4,5；US-EXE-07/AC-1,2  
【Demo】浏览器中从零搭建 M1 工作流并运行、调试

**T2.4 循环节点与 UI**  
【依赖】T2.3  
【产出】​`Loop Start/End`（Row/Chunk/Counting × concat/last/variables）、引擎虚拟循环节点、迭代进度显示、配对校验  
【验收】US-EXE-10/AC-1..4；US-EXE-11/AC-1..4

**T2.5 第二批表格节点**  
【依赖】T2.3  
【产出】​`Joiner`​、​`Concatenate`​、​`GroupBy`​、​`Pivot/Unpivot`​、​`Duplicate Filter`​、​`Missing Value`​、​`Type Cast`​、​`Polars Expression`​、​`Math Formula`​、​`String Manipulation`​、​`Table to Variables`​、​`Variables to Table`​、​`Table Creator`​、​`Table View`​、​`Python Script`​、​`Path Join`​、​`File Copy/Move/Rename/Delete`  
【验收】US-TBL-03..07、US-TBL-08/AC-1..7、US-TBL-10 的全部 P0 AC

---

## M3 Excel 联动

**T3.1 ExcelBackend 接口 + Fake 实现**  
【依赖】T1.3（可与 M2 并行）  
【产出】接口（​`03-architecture.md`​ §5.1）、​`FakeExcelBackend`、描述符、契约测试套件（两实现共用）  
【验收】US-XLS-03/AC-4；契约测试在 Linux CI 绿

**T3.2 ExcelWorker**  
【依赖】T3.1  
【产出】STA 线程、submit 队列、超时放弃、错误映射、RefRegistry、非 Worker 线程断言  
【验收】US-XLS-11/AC-1,2,3；US-XLS-12/AC-1,2,3

**T3.3 XlwingsBackend**  
【依赖】T3.2 + T0.3 结论  
【产出】真实实现：attach/new_hidden、读写区域（类型推断/整块）、cell update、sheet 管理、save、fast_mode  
【验收】US-XLS-01..08、US-XLS-10 的 ​`[int-win]`​ AC（真机脚本 ​`weft-test-win.ps1`）；US-XLS-04/AC-4 与 US-XLS-05/AC-5 性能达标

**T3.4 Excel 节点 + 缓存描述符解析**  
【依赖】T3.3  
【产出】​`Excel Connect/Workbook/Read Range/Write Table/Cell Update/Sheet Names/Sheet/Save`​ 节点；描述符缓存失效重解析  
【验收】US-XLS-11/AC-4；端口视图对 Excel 描述符的展示（US-EXE-06/AC-2）  
【Demo】**场景 A 端到端**：读打开的 Excel → 处理 → 写回打开的 Excel，用户全程不关 Excel

---

## M4 Agent

**T4.1 LLMClient + mock 服务器**  
【依赖】T1.8  
【产出】OpenAI 兼容客户端（流式/重试/用量）、LLM 配置管理 + 测试连接、​`tests/fixtures/mock_llm/`  
【验收】US-AGT-01/AC-1..4；US-AGT-02/AC-5

**T4.2 LLM Call + Prompt Template + 插值**  
【依赖】T4.1  
【产出】两节点 + ​`{var}`​ / ​`{table:port}` 插值 + Jinja2 沙箱  
【验收】US-AGT-02/AC-1..4；US-AGT-09/AC-1..4

**T4.3 Agent Loop + ToolDispatcher + 审计**  
【依赖】T4.2  
【产出】ReAct 循环、Tool 端口、工具去重/超时/错误回填、audit.jsonl、trace.jsonl、​`node.stream`​/​`node.tool_call` 事件、轨迹面板  
【验收】US-AGT-03/AC-1..5；US-SBX-07/AC-1..3；US-AGT-10/AC-1..3

**T4.4 Node as Tool**  
【依赖】T4.3  
【产出】节点包装、ephemeral 执行、result_format、防递归校验  
【验收】US-AGT-04/AC-1..7

**T4.5 Chat 面板与聊天触发**  
【依赖】T4.3  
【产出】​`Chat Input/Output`​、聊天面板、​`chat.message`​ 流式、session 管理  
【验收】US-AGT-07/AC-1..5；US-TRG-03/AC-1,2  
【Demo】**场景 B 端到端**（mock LLM 自动化 + 真实模型手动验收 US-AGT-03/AC-6）

---

## M5 沙箱

**T5.1 Sandbox 接口 + NoneSandbox（影子目录）**   
【依赖】T0.2 结论  
【产出】接口、NoneSandbox、变更收集/应用/丢弃、受保护文件、契约测试  
【验收】US-SBX-01/AC-1..3；US-SBX-05/AC-4（Linux CI 可测）

**T5.2 SandboxieSandbox**  
【依赖】T5.1  
【产出】Start.exe 封装、helper 进程、changes 收集、终止清理、单 Run 互斥  
【验收】US-SBX-02/AC-1..4；US-SBX-03/AC-1..3；US-SBX-06/AC-1（真机）

**T5.3 变更审批流**  
【依赖】T5.1  
【产出】changes API、diff、审批面板、auto_apply_in_root、幂等 apply  
【验收】US-SBX-04/AC-1..4；US-SBX-05/AC-1..3,5

**T5.4 Sandboxed Tools + Pi Agent 节点 + 人工确认**  
【依赖】T5.2 + T4.3 + T0.4 结论  
【产出】五工具、Pi 节点（PiRunner）、confirm 流（事件/API/UI 卡片/超时）  
【验收】US-AGT-05/AC-1..6；US-AGT-06/AC-1..4；US-AGT-12/AC-1..4；US-AGT-11/AC-1..3  
【Demo】**场景 C 端到端**（真机 + 真实模型手动验收 US-AGT-06/AC-5）

---

## M6 触发器 + 打包

**T6.1 TriggerManager + schedule/watch/http**  
【依赖】T1.8  
【产出】统一事件、APScheduler、watchdog（防抖/忽略规则/防自激）、HTTP 触发（token/限速/wait）、来源开关、健康状态  
【验收】US-TRG-01/AC-2,3；US-TRG-04/AC-1..4；US-TRG-05/AC-1..5；US-TRG-06/AC-1..3；US-TRG-07/AC-1,2；US-SBX-09/AC-1..3

**T6.2 打包/导入**  
【依赖】T1.1  
【产出】pack（排除规则/预检/密钥扫描/绝对路径清单）、unpack（zip slip 防护/自动 sync）、CLI 等价命令  
【验收】US-PKG-01/AC-2；US-PKG-03/AC-1..4；US-PKG-04/AC-1..4；US-SBX-08/AC-1..3  
【Demo】**场景 D + E 端到端**：watch 触发自动跑；A 机 pack → B 机 unpack → run 通过

---

## M7 收尾（P1 + 发布）

**T7.1 P1 功能包**：Metanode（US-DES-09）、注释/便签（US-DES-10）、运行历史面板（US-EXE-09）、Memory 节点（US-AGT-08）、Rule Engine（US-TBL-05/AC-4）、Shell Command（US-TBL-09）、Excel Run Macro（US-XLS-09）、运行前预检（US-PKG-07）、绝对路径跳转修改（US-PKG-06）  
**T7.2 doctor 与运维**：​`weft doctor`​/​`--cleanup`​、日志轮转、设置页完整化（US-SET-01..04 全部 AC）  
**T7.3 发布**：真机全量 ​`-m win_real`​、性能指标复测（PRD §9.3）、README/安装文档、CHANGELOG、​`0.1.0` 构建

---

## 里程碑验收总表

|里程碑|自动化门槛|手动门槛|
| --------| ---------------------------------| --------------------------------|
|M1|T1.x 全部 AC 测试绿|CLI demo 录屏|
|M2|e2e 套件绿|10 分钟搭建测试（PRD G1）|
|M3|Fake 契约 + win 真机脚本绿|场景 A 实操|
|M4|mock LLM 套件绿|场景 B 真实模型抽查|
|M5|NoneSandbox 契约绿 + win 真机绿|场景 C 实操审批|
|M6|触发器/打包集成测试绿|双机交接实测（PRD G3）|
|M7|全量 CI + win_real 绿|PRD §4.2 两条成功标准启动跟踪|

全部完成。当前文档集状态：

|文件|内容|状态|
| ------| -----------------------------------------------------| ------|
|`docs/01-prd.md`|定位、场景、功能需求、Non-goals、决策 D-01..13|完成|
|`docs/02-user-stories.md`|88 个故事、9 个 Epic、覆盖矩阵|完成|
|`docs/03-architecture.md`|进程拓扑、引擎、IPC、Excel/Agent/沙箱、ADR A-01..10|完成|
|`docs/04-data-model.md`|workflow.json、端口类型、ValueRef、config.toml|完成|
|`docs/05-api.md`|REST + WS 契约、错误码、事件目录|完成|
|`docs/06-engineering.md`|工具链、测试分层、Git 规范、agent 约定|完成|
|`docs/07-roadmap.md`|M0–M7 里程碑、31 张任务卡|完成|
|`CLAUDE.md`|agent 入口索引与硬性规则|完成|

还缺一份规划中的 ​**​`06-nodes-v1.md`​**​ **（节点参数级规格）** ——文档间多处引用了它（Pi 命令行、各节点 params schema 的权威定义）。它篇幅会很大，建议的替代方案：不单独预写，在 roadmap 各任务卡实现节点时，以代码中的 JSON Schema 为准、由脚本导出成文档。如果你希望先写再实现，告诉我。

另外提醒两点：

1. **文档中的部分技术假设尚未验证，不能直接当作既定事实。**   
   尤其是三项：

   - Sandboxie 能否可靠收集新增、修改、删除、重命名等变更；
   - xlwings 在多个 Excel 实例、已打开工作簿、COM 忙碌状态下的真实行为；
   - pi 当前版本的非交互调用方式、输出格式和参数。

   因此应先执行 ​**M0 的三个 spike**。如果验证结果与文档冲突，先修改架构、验收标准和任务卡，再进入正式实现，避免 agent 按错误假设写出大量代码。
2. **当前 v1 范围已经接近一个完整的中型产品，不要一次性交给 agent 全量实现。**   
   建议把第一阶段进一步收敛为 ​**M0 → M1 → M2 → M3**：先做出“画布设计 → 表格处理 → Excel 实时读写 → 缓存与局部执行”的可用产品；确认你确实愿意日常使用后，再做 Agent 和 Sandboxie。否则很容易在底层引擎、UI、Excel、Agent、沙箱五条战线上同时铺摊子，最后每条都只能演示、不能实用。
