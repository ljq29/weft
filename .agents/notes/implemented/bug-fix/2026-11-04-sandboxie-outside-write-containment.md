# Agent Note: Sandboxie Root 外写入采用遏制与审计降级

Status: implemented

## Problem

安全 AC 原先要求任意沙箱命令写入 Root 或显式授权范围之外时被硬拒绝。真实 Sandboxie-Plus 5.72.5 的全盘 `ReadFilePath`，以及 `ClosedFilePath` + Root `NormalFilePath` + 运行时目录只读的组合，都使 Python/helper 无法正常启动。单纯接受 Sandboxie 默认重定向虽然能保持真实路径不变，却会把外部变更当成普通可应用变更，并可能错误报告审计完整。

## Decision

任意命令的 Root 外写入采用遏制与审计降级，不再宣称硬拒绝。Sandboxie 写入只落在本 Run Box；真实路径必须保持不变。收集器同时识别 `drive\` 和 `user\current` 映射，将授权范围外的变更标记为 `protected`，记录明确警告并设置 `audit_complete=false`。审批层已有 protected 整体拒绝逻辑，因此这些外部变更不得应用到真实位置。

文件 helper 仍在启动前执行应用层路径授权，未授权请求直接失败。任意用户命令不得因启动竞争自动重放；只有确认包装器从未创建输出文件的内部 helper 才可重试。调整后的行为 AC 同步记录在 `docs/01-prd.md`、`docs/02-user-stories.md` 和 `docs/03-architecture.md`。

## Alternatives considered

1. **全盘 `ReadFilePath` + Root `NormalFilePath`**：配置最简单，理论上能让 Root 外只读、Root 内正常重定向；实测使 Python/helper 启动失败，因此放弃。
2. **全盘 `ClosedFilePath` + Root Normal + 运行时目录只读**：这是最接近原硬拒绝要求的方案；组合仍使 Python/helper 无法运行，因此放弃。
3. **只保留默认重定向，不增加 protected 与审计警告**：实现最少，真实路径也不变，但外部变更仍可能被应用，且审计完整性会被误报，因此不可接受。

## Consequences

收益是越权写入不会改变宿主真实文件，外部变更无法经审批落地，并且用户能看到审计不完整警告。代价是沙箱内写命令可能返回退出码 0，这不是硬拒绝成功；外部变更只用于展示风险，不提供正常恢复路径。需要正常写外部目录的用户必须显式配置授权 Root。

该决定收窄了安全承诺，但没有允许真实路径直写。若未来找到可同时运行 Python/helper 的硬拒绝配置，应新开决策记录并恢复更严格的 AC，不在本篇中把决定改回反面。

## Verification

- `packages/weft/tests/test_sandboxie_real.py` 验证真实外写后宿主文件不存在、外部变更 protected、审批拒绝且 `audit_complete=false`。
- 同一真实套件覆盖创建、删除、重命名、默认断网、环回代理、COM 隔离、跨 Run 清理、正常审批与 stale 冲突。
- 真实 Pi 文件生成和审批闭环通过，运行产物不含原始 API key。
- 最终回归通过：173 项后端、23 项前端、36 项集成、12 项 `win_real`、11 项 E2E；无 Excel 或活动测试 Box 残留。

## 记录审计

写入前检查时仓库不存在 `.agents/notes`，没有需要互链、吸收或归档的既有决策记录。
