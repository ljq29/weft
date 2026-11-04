# Agent Note: Nuitka 绿色目录内置独立工作流运行时

Status: implemented

## Problem

仅把 CLI 编译成 `weft.exe` 会使 `sys.executable` 指向 EXE，现有 ExcelWorker、Sandboxie helper 和 doctor 仍按 Python 解释器调用它，导致真实功能失败。若绿色版只内置主服务而继续依赖宿主 Python/uv，则无法在无开发环境的 Windows 机器上执行工作流。

## Decision

绿色目录 `weft-windows-x64/` 同时包含四部分：Nuitka standalone 主程序、安装了同版本 Weft 的完整 Python 运行时、三个本地 wheel、以及 `tools/uv.exe`。`scripts/build_portable.py` 统一构建目录和 `weft-windows-x64.zip`，保留 wheel 作为另一种发布形式。

`weft.portable.python_executable()` 是内部 Python 子进程的唯一入口。ExcelWorker、Sandboxie 和 doctor 使用内置 Python，不再直接使用编译后的 `sys.executable`。`WorkflowEnvironment.run_uv()` 使用内置 uv，并设置 `UV_PYTHON` 指向内置 Python、`UV_FIND_LINKS` 指向本地 wheel；其他依赖仍通过配置的 Python 镜像获取。普通源码和 wheel 安装继续沿用宿主环境。Nuitka 不包含可供 `inspect.getsource()` 读取的 Python 源文件时，节点缓存实现哈希回退到“模块、类名、发布版本”，发布升级仍会正确失效缓存。

绿色版验收必须模拟不含 Python/uv 的 PATH，真实执行 CSV 工作流，并启动服务验证鉴权 API 和前端静态页。发布流水线接入同一验收脚本，不能只检查 `weft.exe --version`。

## Alternatives considered

1. **Nuitka onefile**：分发文件更少，但只是自解压目录，启动慢且内部子进程路径更复杂，因此选择 standalone 目录后 zip。
2. **只编译主服务并依赖宿主 Python/uv**：产物更小，但不满足绿色目录在无开发环境机器上运行工作流的目标，因此不采用。
3. **让所有内部子进程经过 `weft.exe` 自定义命令**：可以减少一个 Python 运行时，但会把 ExcelWorker、Sandboxie helper 和 doctor 的协议耦合进 CLI，且工作流仍需要独立 Python，因此不采用。
4. **把所有第三方依赖 wheel 都打入 ZIP 并完全离线**：能进一步消除首次联网，但显著增加体积和多版本锁维护成本；当前只保证免预装 Python/uv，其他工作流依赖允许按锁文件下载。

## Consequences

收益是解压后即可运行 CLI、UI、内部 helper 和真实工作流，主服务与 Worker 仍保持独立环境和精确版本约束。代价是 ZIP 明显大于三个 wheel，首次创建或升级工作流环境仍可能需要联网；Excel、Sandboxie、Node.js/pi 继续是外部依赖，代码签名和 SmartScreen 信誉也独立处理。

## Verification

- `packages/weft/tests/test_portable.py` 覆盖便携与开发环境的路径选择。
- `scripts/verify_portable.py` 在仅含 `System32` 的 PATH 下验证 `weft.exe --version`、真实 CSV 工作流、服务鉴权 API 和前端页面。
- `v0.1.1` 本机验收通过：无宿主 Python/uv 的 CSV、服务 API、前端和 `weft.exe doctor --json` 均成功，Excel COM 与 Sandboxie 探针 `fail_count=0`。
- `weft-windows-x64.zip` 完整性与解压测试通过，解压目录再次执行相同核心验收成功；Release 下载 ZIP 后仍需重复该验收。

## 记录审计

写入前检索了现有 `.agents/notes`；[标签发布流程](../process/2026-11-04-tag-driven-github-release.md) 与本篇部分重叠，发布侧资产变化在该篇同步，本篇只持有便携运行时架构。MIT、Windows-only 验证和 Sandboxie 外写遏制记录无需修改。
