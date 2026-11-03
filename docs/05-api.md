# 05-api.md

**Weft API 契约（REST + WebSocket）**

|项|值|
| --------| --------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`02-user-stories.md`、`04-data-model.md`|
|消费方|前端 UI、CLI、外部 HTTP 触发方|

约定：前缀 `/api`；请求/响应均为 `application/json`（除注明 Arrow 流处）；时间为 ISO 8601 带时区；错误统一结构：

```jsonc
// 非 2xx 响应体
{"error": {"code": "WORKFLOW_NOT_FOUND", "message": "人类可读", "detail": {...}}}
```

|HTTP 状态|场景|
| -----------| ------------------------------------------------------------|
|400|参数/校验错误（含受保护文件 apply）|
|401|token 缺失或错误|
|403|缺少 `X-Weft-Client: ui`，或 Host/Origin 校验失败；令牌本身缺失/无效仍为 401|
|404|资源不存在（HTTP 触发未启用也返回 404，见 US-TRG-06 AC-3）|
|409|状态冲突（运行期改图、revision/CAS 不一致、队列满）；批量 apply 的逐项 `CHANGE_CONFLICT` 通过 200 结果返回，重复 apply 幂等|
|422|workflow.json schema 校验失败（detail 含逐条错误）|
|202|异步接受（触发运行）|

鉴权与浏览器边界：服务启动时生成随机 UI 会话令牌，自动打开的启动 URL 携带该令牌；前端仅将其保存在 `sessionStorage`，REST 使用 `Authorization: Bearer <ui_session_token>`，WS 连接后先发送 `{"op":"authenticate","token":"..."}`，认证成功才能订阅。CLI 从仅当前用户可读的会话文件取得令牌。监听 `127.0.0.1` 时，除使用工作流 Bearer token 的 `/trigger` 外，其余 `/api/*` 均要求 UI 会话令牌；监听非本机时改用 `Authorization: Bearer <global_token>`（US-SBX-09）。

所有请求校验 Host 是否属于配置的本机监听地址；浏览器请求还须校验 Origin 为当前 UI 同源地址，失败返回 403。无 Origin 的非浏览器请求必须持有对应 Bearer token。图结构修改接口还要求头 `X-Weft-Client: ui`；该头只用于区分 UI 改图操作、减少误调用，不替代鉴权，也不构成 agent 不得改图的安全边界（US-AGT-11 AC-2）。

---

## 1. 工作流管理

|方法|路径|说明|
| --------| ------| -----------------------------------------------------------------------------------|
|GET|`/api/workflows`|已打开的工作流列表：`[{id, name, path, dirty, env_status}]`|
|POST|`/api/workflows`|新建：`{name, parent_dir}` → 201 `{id, path}`；同名目录存在 → 409|
|POST|`/api/workflows/open`|打开已有目录：`{path}` → `{id, env_status: ok\|syncing\|error}`；触发 `uv sync`（US-PKG-02）|
|GET|`/api/workflows/{id}`|返回完整 `workflow.json` 文档|
|PUT|`/api/workflows/{id}`|整文档保存（前端自动保存用），携带读取时的 `revision`；成功递增 revision，CAS 冲突或 Run 活跃时改图结构 → 409；校验失败 422|
|PATCH|`/api/workflows/{id}`|局部更新（JSON Merge Patch + 读取时 `revision`）：位置、注释等非结构字段在 Run 活跃时允许，仅影响下一 Run；CAS 冲突 → 409|
|DELETE|`/api/workflows/{id}`|从服务关闭（不删目录）；`?purge_cache=true` 顺带清缓存|
|POST|`/api/workflows/{id}/duplicate`|本机复制：生成新目录、workflow id 与 revision 历史，不复制 `.runs/`、`.venv/` → 201 `{id, path, revision}`；目标目录冲突 → 409|
|GET|`/api/workflows/{id}/validate`|返回校验结果 `{errors: [...], warnings: [...]}`（规则见 `04-data-model.md` §2）|
|GET|`/api/workflows/{id}/env`|环境状态：`{status, python, uv_output}`|
|POST|`/api/workflows/{id}/env/sync`|手动触发 `uv sync`；进度经 WS `env.progress`|

## 2. 节点类型

|方法|路径|说明|
| ------| ------| --------------------------------------------------------------------------|
|GET|`/api/nodes/types`|全部可用节点类型（内置 + 当前工作流 `user.*`）：`[{type, node_version, category, name, description, lane, cache_policy, tool_capability, tool_exposed_params, inputs, outputs, params_schema, ui_hints, portable_params, external_resources}]`（US-DES-04 AC-4、US-AGT-04 AC-1）|
|GET|`/api/nodes/types/{type}`|单个类型详情|
|POST|`/api/workflows/{id}/nodes/{node_id}/column-hints`|返回该节点各输入端口上游缓存的列名（表单下拉用）：`{port: [col, ...]}`；上游未执行 → 空|

## 3. 运行

|方法|路径|说明|
| ------| ------| ------------------------------------------------------------------|
|POST|`/api/workflows/{id}/runs`|发起运行：`{scope: {kind: all\|to_node\|from_node\|single, node_id?}, overrides?: {k: v}}`。立即执行或入队 → 202 `{run_id, disposition: started\|queued}`；`drop` 策略丢弃 → 200 `{run_id: null, disposition: dropped}` 并记录日志；队列满 → 409 `RUN_QUEUE_FULL`。未配置节点存在 → 400（detail 列出）|
|GET|`/api/workflows/{id}/runs?status=&limit=20`|运行历史（US-EXE-09）|
|GET|`/api/runs/{run_id}`|Run 详情 = `meta.json` 内容（`04-data-model.md` §6）|
|POST|`/api/runs/{run_id}/cancel`|取消 → 202；已终态 → 409|
|POST|`/api/runs/{run_id}/confirm`|`{request_id, decision: approve\|reject, modified_args?}`（US-AGT-12）|
|GET|`/api/runs/{run_id}/log?offset=0&limit=500&level=&node_id=`|分页日志|
|GET|`/api/runs/{run_id}/audit`|审计记录列表（US-SBX-07）|
|GET|`/api/runs/{run_id}/nodes/{node_id}/trace`|agent 轨迹（trace.jsonl 内容）|

## 4. 节点状态与缓存操作

|方法|路径|说明|
| ------| ------| ------------------------------------|
|POST|`/api/workflows/{id}/nodes/{node_id}/reset`|重置本节点及下游（US-EXE-03 AC-3）|
|POST|`/api/workflows/{id}/reset`|重置全部|
|GET|`/api/workflows/{id}/nodes/{node_id}/status`|`{status, from_cache, last_run_id}`|

## 5. 端口数据预览

|方法|路径|说明|
| ------| ------| ------------------------------------------------------------------------------------------------------|
|GET|`/api/workflows/{id}/nodes/{node_id}/ports/{port}`|读取最近一次有效执行的端口输出。Table：`?offset=0&limit=100&sort_by=&desc=` → `Content-Type: application/vnd.apache.arrow.stream`（切片后的 Arrow IPC）+ 头 `X-Weft-Total-Rows`；其他类型 → JSON|
|GET|`/api/runs/{run_id}/nodes/{node_id}/ports/{port}`|同上，但严格读取 `meta.json` 中的 ValueRef：内联小 JSON 直接读取，文件值只从 `.runs/<run_id>/outputs/` 读取；不读临时 IPC 或当前全局缓存|

未执行 → 404 `PORT_NOT_EXECUTED`（US-EXE-06 AC-5）。v1 不预建排序索引：未指定 `sort_by` 时按 Arrow record batch 定位分页；指定排序时允许全量读取并稳定排序，响应仍受分页大小限制。该成本必须在 UI 与性能记录中说明，不把排序分页宣称为常量时间操作。

## 6. 沙箱变更审批

|方法|路径|说明|
| ------| ------| ------------------------------------------------------------------------------------------|
|GET|`/api/runs/{run_id}/changes`|`changes.json` 内容（`04-data-model.md` §8），含 `audit_complete`、基线哈希、重命名与逐项状态|
|GET|`/api/runs/{run_id}/changes/diff?path=`|文本文件 unified diff：`{old: str\|null, new: str\|null, diff: str}`；二进制 → 400|
|POST|`/api/runs/{run_id}/changes/apply`|`{paths: [...], overwrite_conflicts?: bool}`。请求已处理 → 200 `{results: [{path, status: applied\|conflict\|failed, error?}]}`，部分成功与部分冲突可以同时存在；含 protected 路径等整体请求错误 → 400。apply 前重算目标哈希，变化则该项 `status: conflict, error: {code: CHANGE_CONFLICT}`；只有用户查看新 diff 后显式 `overwrite_conflicts: true` 才覆盖。重复 apply 幂等|
|POST|`/api/runs/{run_id}/changes/discard`|丢弃全部未应用变更；已应用项保持已应用记录|

## 7. 触发

|方法|路径|说明|
| ------| ------| --------------------------------------------------------------------------|
|POST|`/api/workflows/{id}/trigger`|外部 HTTP 触发（US-TRG-06）。`Authorization: Bearer <workflow_token>`；body 任意 JSON。立即执行/入队 → 202 `{run_id, disposition}`，队列满 → 409。`?wait=true` 同步等待至多 `trigger.http_wait_timeout_s`；正常结束 → `{run_id, status, outputs}`，唯一已执行的 `HTTP Response` 提供 `outputs: {status_code, headers, body}`，未执行时 outputs 为 `{}`；等待超时但 Run 仍 queued/running → 202 `{run_id, status, outputs: {}, wait_timed_out: true}`，Run 继续执行；drop（无论是否 wait）→ 200 `{run_id: null, disposition: dropped}`，不返回 status/outputs；同一 Run 执行多个响应节点则运行失败|
|POST|`/api/workflows/{id}/trigger/token`|生成/轮换 workflow token（需 UI 会话鉴权），返回明文一次|
|GET|`/api/workflows/{id}/triggers/status`|各来源状态：`{manual: {enabled}, schedule: {enabled, next_fire_times: [...]}, watch: {enabled, health: ok\|error, error?}, ...}`；TriggerManager 从 Trigger 节点 params 派生运行视图|

## 8. 聊天

发送固定走 REST，经 `ChatSource` 进入统一触发队列；WS 只负责服务端推送，不接收聊天命令。

|方法|路径|说明|
| ------| ------| ------------------------------------------------------------------------------------|
|POST|`/api/workflows/{id}/chat`|`{message, session_id?}` → 202 `{run_id, session_id, disposition: started\|queued}`；drop → 200 `{run_id: null, session_id, disposition: dropped}`；队列满 → 409。未启用 chat 触发 → 400 `CHAT_DISABLED`（面板据此显示提示，US-TRG-03 AC-2）|
|GET|`/api/workflows/{id}/chat/{session_id}`|读取 `.runs/chat/<session_id>.jsonl` 的 UI 会话记录（含历次 Run 的 Chat Output），不等于 P1 Memory 节点数据|
|POST|`/api/workflows/{id}/chat/{session_id}/clear`|清空 UI 会话记录；是否同时清空 P1 Memory 由独立 `clear_memory: bool`（默认 false）控制|

## 9. 打包与导入

|方法|路径|说明|
| ------| ------| --------------------------------------------------------------------------------------|
|POST|`/api/workflows/{id}/pack`|`{exclude_data: bool, confirm_warnings?: bool, output?: str}` → `{job_id, path}`；任何 schema、Loop 等 ERROR 都阻断，不能用 force 跳过；只有 WARNING 可在 `confirm_warnings: true` 后继续|
|GET|`/api/workflows/{id}/pack/preflight`|打包预检报告：`{errors, warnings, abs_paths: [{node_id, param, value}], size_estimate}`|
|POST|`/api/workflows/unpack`|`{zip_path, dest_dir}` → `{id, path}`；zip slip → 400；导入保留 workflow id，本机“复制工作流”操作另生成新 id|

## 10. 设置与系统

|方法|路径|说明|
| -----------| ------| ----------------------------------------------------------|
|GET / PUT|`/api/settings`|用户级配置（api_key 读取时掩码；PUT 时 `"***"` 表示不变更）|
|POST|`/api/settings/llm/{name}/test`|测试连接（US-AGT-01 AC-2）|
|GET|`/api/system/doctor`|`weft doctor` 的 JSON 输出|
|GET|`/api/system/version`|`{version, schema_version}`|
|POST|`/api/fs/browse`|服务端文件选择器：`{path, dirs_only}` → 目录列表（表单路径选择用）|

## 11. WebSocket

`WS /api/ws`（单连接多路复用，连接后先认证再订阅）：

```jsonc
// 客户端 → 服务端
{"op": "authenticate", "token": "<ui_session_token>"}
{"op": "subscribe",   "topics": ["workflow:wf_8f3a", "run:r_2025..."]}
{"op": "unsubscribe", "topics": [...]}

// 服务端 → 客户端（统一信封）
{"topic": "system", "event": "subscribed", "data": {"topics": ["run:r_..."]}}
// subscribe 生效后先返回 ACK；以下为运行事件
{"topic": "run:r_...", "event": "node.started", "ts": "...", "data": {...}}
```

事件目录（`data` 字段）：

|event|data|对应 AC|
| -------------| --------------------------------------------------------------| ----------------|
|`run.started`|`{run_id, scope}`|US-EXE-05|
|`run.finished`|`{run_id, status, usage}`||
|`run.queued` / `run.dequeued`|`{run_id, position}`|US-EXE-13|
|`node.status`|`{node_id, status}`（unconfigured/configured/running/executed/failed/cancelled/out_of_scope/skipped_branch/skipped_upstream）；out_of_scope 与失败后的 skipped_upstream 在 UI 显示 configured，skipped_branch 显示灰色 skipped|US-DES-05|
|`node.started` / `node.finished`|`{node_id, duration_ms?, from_cache?}`||
|`node.failed`|`{node_id, error: {code, type, message}}`（完整 traceback 走 REST，code 见 §12）|US-EXE-07|
|`node.progress`|`{node_id, fraction, message?}`||
|`node.log`|`{node_id, level, message}`||
|`node.stream`|`{run_id, node_id, session_id?, source_node_id, delta}`|US-EXE-05 AC-2|
|`node.tool_call`|`{run_id, node_id, tool, args_redacted, status, duration_ms, result_summary}`|US-AGT-03 AC-5|
|`node.confirm_request`|`{request_id, run_id, node_id, tool, args, timeout_at}`|US-AGT-12|
|`node.iteration`|`{run_id, loop_node_id, index, total}`|US-EXE-10 AC-3|
|`chat.message`|`{run_id, session_id, source_node_id, message_id, role, content, streaming: bool}`|US-AGT-07|
|`changes.ready`|`{run_id, count, audit_complete}`|US-SBX-04|
|`env.progress`|`{workflow_id, line}`（uv 输出逐行）|US-EXE-14 AC-1|
|`pack.finished`|`{job_id, path}` / `pack.failed`|US-PKG-03|
|`workflow.saved`|`{workflow_id, modified_at, revision}`（多标签页同步；revision 不一致时重新读取，不盲写）||
|`trigger.status`|`{workflow_id, source, health}`|US-TRG-05 AC-4|

聊天 UI 以 `(run_id, source_node_id, message_id)` 关联 `node.stream` 与 `chat.message`；最终 Chat Output 消息与增量共用同一 message_id，前端替换而非重复追加。WS 无事件回放，重连后用 REST 补齐（US-EXE-05 AC-3）。

## 12. 错误码目录

所有非 2xx 响应必须返回稳定的机器可读 `error.code`；Run 内节点失败在 `meta.json` 的 `error.code` 使用同一目录，API 层不把它伪装成同步 HTTP 异常。前端和测试不得匹配自然语言消息来代替 code。目录至少包含：

|code|HTTP / 记录位置|含义 / 是否可重试|
| ------| ------| ----------------|
|`WORKFLOW_NOT_FOUND`|404|工作流不存在；否|
|`VALIDATION_ERROR`|400 / 422|参数或 schema 校验失败，detail 含逐条错误；修改后重试|
|`REVISION_CONFLICT`|409|revision/CAS 不一致；重新读取后决定|
|`RUN_ACTIVE`|409|活跃 Run 禁止结构修改；当前 Run 结束后重试|
|`RUN_QUEUE_FULL`|409|触发队列已满；稍后重试|
|`PORT_NOT_EXECUTED`|404|端口没有可读取的有效输出；执行后重试|
|`CHAT_DISABLED`|400|聊天触发未启用；启用后重试|
|`CHANGE_CONFLICT`|200 逐项|真实目标已变化；查看新 diff 并显式覆盖|
|`LLM_CONFIG_NOT_FOUND`|Run 节点错误|命名 LLM 配置不存在；配置后重试|
|`NONE_SANDBOX_DISABLED`|400 / Run 节点错误|NoneSandbox 未获全局允许；修改设置后重试|
|`BASH_REQUIRES_SANDBOXIE`|400 / Run 节点错误|none 模式选择 bash；改用 sandboxie|
|`PI_REQUIRES_SANDBOXIE`|400 / Run 节点错误|none 模式选择 Pi Agent；改用 sandboxie|
|`EXCEL_WORKER_RESTARTED`|Run 节点错误|ExcelWorker 已重建，排队/在途请求结果未知；写操作不得自动重放|
|`EXCEL_UNAVAILABLE`|Run 节点错误|Excel 不可用或仍繁忙；排除故障后重试|
|`UNAUTHORIZED`|401|Bearer/UI/WS 令牌缺失或无效；更新凭据|
|`FORBIDDEN`|403|Host/Origin 或 UI 操作标记校验失败；修正请求|

新增错误码必须同步对应 AC；消息可改进，code 在 1.0 后按兼容性承诺管理。

## 13. 兼容性承诺

- 0.x 阶段 REST/WS 允许破坏性变更；1.0 起只新增端点、事件和可选字段，删除、重命名或改变语义需升主版本。
- `schema_version` 只描述工作流数据格式与迁移，不是 API 兼容性的替代品；`/api/system/version` 同时返回服务版本与 schema_version。
- CLI 的 `--json` 输出结构与对应 REST 响应一致。
