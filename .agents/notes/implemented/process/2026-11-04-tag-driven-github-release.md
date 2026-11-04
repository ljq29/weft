# Agent Note: GitHub Release 由版本标签驱动

Status: implemented

## Problem

普通 CI 只上传临时 wheel 构建产物，不能形成可追踪的正式发布。手工创建 Release 容易遗漏测试、使用错误源码或上传与标签版本不一致的包。

## Decision

`.github/workflows/release.yml` 在推送 `v*.*.*` 标签时运行。标签去掉首字母 `v` 后必须与 `weft.__version__` 完全一致；主服务、Worker 和 SDK 使用同一版本。Release 任务在 Windows 上依次执行 `poe check`、集成测试、前端构建、Playwright E2E 和三个 wheel 构建，全部成功后才使用 GitHub CLI 创建 Release 并上传 wheel。

Release 使用标签对应的提交和 `contents: write` 权限。真实 Excel/Sandboxie 的 `win_real` 仍在本机登录态验收，不伪装成 hosted runner 能力。版本发布不自动勾选 `T7.10`，完整 v1 的人工交接和采用指标独立追踪。

## Alternatives considered

1. **本地手工执行 `gh release create`**：操作直接，但容易跳过测试或上传错误产物，也不具备远程可复查的统一过程，因此改为标签流水线。
2. **每次推送 `main` 都创建 Release**：能进一步减少手工步骤，但会产生无版本意图的发布，因此保留显式版本标签作为发布动作。
3. **只构建 wheel，不运行完整 E2E**：发布更快，但会削弱发布产物与已验证行为之间的对应关系，因此不采用。

## Consequences

收益是版本、源码提交、测试结果和 Release 产物形成可复查的对应关系，发布动作只需提交版本变更并推送匹配标签。代价是每次发布都运行完整自动化，耗时高于单纯构建； hosted CI 不覆盖真实桌面 Excel/Sandboxie，发布记录必须保留本机 `win_real` 证据和未完成的人工门禁。

## Verification

- 标签与包版本不一致时，发布在构建前失败。
- Release 创建依赖全部测试、E2E 和 wheel 构建成功。
- 首次实施版本为 `v0.1.0`，GitHub Actions 运行 `41791135262` 成功，Release 位于 `https://github.com/ljq29/weft/releases/tag/v0.1.0`。
- Release 包含 `weft`、`weft-worker`、`weft-sdk` 三个 wheel；下载资产与本地构建逐字节一致，隔离环境安装及两个 CLI 的 `--version` 均验证为 `0.1.0`。

## 记录审计

写入前检索了现有 `.agents/notes`；MIT、Windows-only 验证和 Sandboxie 外写遏制记录均不持有发布流程决定，无需互链、吸收或归档。
