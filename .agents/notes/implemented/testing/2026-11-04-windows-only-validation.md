# Agent Note: Weft 仅在 Windows 上验证与支持

Status: implemented

## Problem

工程文档和 CI 曾同时声明 Linux 与 Windows 验证，但产品 v1 的真实目标平台只有 Windows，WSL/Linux 不能验证 Excel COM、Sandboxie、Windows 进程信号和路径行为。保留双平台门禁会让替身环境通过被误读为产品可运行，并增加不受支持平台的维护成本。

## Decision

Weft 的开发、测试、E2E、wheel 构建和 GitHub Actions 统一在 Windows 上运行，不再声明或维护 WSL/Linux 支持。删除 Linux mypy 目标和 Ubuntu CI 矩阵，Playwright 在 Windows 安装 Chromium 时不使用 Linux 专用的 `--with-deps`。Python 依赖仍通过清华镜像获取，pnpm 使用 npmmirror。`.gitattributes` 统一文本文件为 LF，避免 Windows runner 的 CRLF 检出与 Prettier 配置冲突。

Fake Excel、NoneSandbox 和 Mock LLM 继续保留：它们用于 Windows CI 隔离不可控外部依赖，不代表 Linux 支持，也不能替代本机登录态的 `win_real` 验收。PRD 中非目标章节继续明确不支持 macOS/Linux。

## Alternatives considered

1. **保留 Linux + Windows 双平台 CI**：能多验证纯 Python 逻辑，但当前产品明确只支持 Windows，且额外平台会制造支持预期和维护成本，因此取消。
2. **用 WSL 代替 Windows CI**：WSL 便于运行类 Unix 工具，但无法覆盖真实 Excel COM、Sandboxie 和 Windows 原生进程语义，因此不作为验收环境。
3. **删除所有 Fake 与契约测试**：可以让测试更贴近真机，但会使普通 PR 强依赖桌面 Excel 和 Sandboxie，降低反馈稳定性，因此保留其 Windows 自动化用途。

## Consequences

收益是文档、CI 与真实支持范围一致，所有自动化都在目标操作系统上执行。代价是失去其他 Unix 环境的额外回归信号；若未来重新支持 Linux，必须重新评估 Excel/Sandboxie 替代实现、平台测试和发布范围，而不能只恢复 CI 矩阵。

## Verification

- `.github/workflows/ci.yml` 的所有 job 仅使用 `windows-latest`。
- `pyproject.toml` 仅保留 `mypy --platform win32`。
- `uv run poe check`、Windows 集成测试、Playwright E2E、wheel 构建和远程 CI 是统一门禁；真实 Excel/Sandboxie 仍由 `win_real` 单独验收。

## 记录审计

写入前检索了现有 `.agents/notes`；Sandboxie 外写遏制记录涉及运行时安全，与本平台测试决定无关，无需互链、吸收或归档。
