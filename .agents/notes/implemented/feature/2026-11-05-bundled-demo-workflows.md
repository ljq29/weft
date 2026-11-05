# Agent Note: 内置可移植 demo 工作流

Status: implemented

## Problem

新用户需要从空白画布理解节点、连线和端口预览，学习成本较高。仅在前端展示示意图不能验证真实 Worker、数据文件和环境隔离；让示例直接引用开发机路径或包索引又会使 zip 离开本机后失效。

## Decision

Weft 在 `weft.demos` 包资源中携带完整的 `.weft` 目录，并提供示例清单和实例化 API。每次实例化复制到用户选择的父目录，生成新的工作流 ID，再同步独立 `.venv` 后打开；内置资源永不直接作为用户编辑目标。

CSV 与表格 demo 自带所需数据，LLM demo 只引用命名配置，并在画布便签中使用 `<YOUR_API_KEY>` 等占位符，真实密钥仍只存在用户级设置。每份 demo 的 `vendor/` 携带同版本 Worker/SDK wheel，`pyproject.toml` 与 `uv.lock` 只使用 demo 内相对路径引用它们，使 zip 迁移不依赖 Weft 包已发布到公共索引。

## Verification

后端测试覆盖三份 demo 的图校验、独立 ID、冲突拒绝、密钥占位、zip 内容及锁文件可移植性。Playwright 实际创建并运行 CSV 和表格 demo，检查输出文件和聚合预览；LLM demo 验证设置说明。两个离线交互 demo 的 zip 在新临时目录完成 unpack、sync 和真实运行，wheel 包内资源也经过直接实例化验证。

## Alternatives considered

1. **前端硬编码节点 JSON**：实现较少，但无法自带文件、生成依赖锁或完成后端环境同步，因此不采用。
2. **直接打开安装目录中的示例**：省一次复制，但用户修改会污染后续实例，绿色安装目录也可能只读，因此不采用。
3. **从 PyPI 解析 Worker/SDK**：能减少 vendor 重复，但当前分发以 GitHub Release 和本地 wheel 为主，公共索引可用性不能作为前提，因此不采用。

## Consequences

收益是示例与真实执行路径一致，zip 具备自包含的 Weft 运行时包，用户可复制后安全修改。代价是每份 demo 重复携带约 20 KB 的 wheel，版本升级必须同步重建 vendor 和锁文件；Polars、Arrow 等第三方依赖仍按锁文件从缓存或配置的包索引安装。真实 LLM 调用需要用户自己的端点和密钥，不由占位配置冒充验收。

写前检索了 `.agents/notes` 的发布、运行时、Windows 验证和沙箱记录；它们不持有 demo 实例化或资源打包决定，无需互链、吸收或归档。
