# Agent Note: Weft 使用 MIT 许可证

Status: implemented

## Problem

项目准备公开到 GitHub 并接收工作流交接，需要明确使用、修改、商用和再分发权限。未声明许可证时，代码公开并不等于授予这些权利。

## Decision

Weft 源码使用 MIT License。根目录 `LICENSE` 保存标准全文，版权主体写为 `Weft contributors`；根 workspace 和三个 Python 包的 `pyproject.toml` 均声明 `license = "MIT"`。Microsoft Excel、Sandboxie-Plus、Node.js 及其他第三方依赖继续遵循各自许可证，Weft 不把 MIT 授权扩大到这些外部产品。

## Alternatives considered

1. **Apache-2.0**：提供明确的专利授权与反诉讼条款，适合专利风险较高的项目；但条款和 NOTICE 管理更复杂，当前项目更重视简单与低接入成本，因此不采用。
2. **GPLv3**：能要求衍生作品继续开放源码；但会提高闭源商用和内部交接的合规成本。Weft 仅以外部进程调用 Sandboxie，不分发其代码，没有因此采用 GPL 的必要。

## Consequences

收益是使用者可以低门槛地使用、修改、商用和再分发 Weft，同时保留版权与许可声明。代价是 MIT 不提供明确的专利授权，也不要求衍生作品开源；若未来项目需要明确的专利保护，应另开决策记录评估许可证迁移及贡献者授权。

## Verification

- `LICENSE` 为 MIT 标准文本。
- 根目录及 `packages/weft`、`packages/weft-worker`、`packages/weft-sdk` 的包元数据均声明 MIT。
- wheel 构建与安装检查验证许可证声明不破坏打包。

## 记录审计

写入前检索了现有 `.agents/notes`；唯一的 Sandboxie 外写遏制记录与本许可证决定无关，无需互链、吸收或归档。
