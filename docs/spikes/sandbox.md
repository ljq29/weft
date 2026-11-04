# Sandboxie Windows 真机 Spike

## 当前实测环境与结果

- Sandboxie-Plus `5.72.5` 位于 `C:\Program Files\Sandboxie-Plus`，`SbieDrv` 与 `SbieSvc` 正在运行。
- 2026-11-04 已修复最小启动：合法且已创建的 Box 中，`cmd /c exit 0` 和 Python `print(1)` 均正常退出。
- `uv run pytest packages/weft/tests/test_sandboxie_real.py -q`：4 项真实测试通过，覆盖 helper 读写、创建/删除审计、未授权 helper 路径拒绝、默认外网阻断、环回代理例外、COM 拒绝、跨 Run 清理、真实审批应用与 stale 冲突。
- 真实 Pi 已在 Sandboxie 内完成文本任务和文件创建；审批前真实目录不变，审批应用后内容正确，运行产物不含原始 API key。
- `weft doctor` 已实际执行动态 Box、Python stdout 和默认断网探针，不再只检查 `Start.exe` 是否存在。
- 通过 `create_sandbox(..., "sandboxie")` 工厂入口实际启动 Python，退出码和 stdout 均正确。
- 测试后 `SbieIni.exe queryex /boxes *` 仅剩 `DefaultBox`，测试 Box 未残留。

## 根因与修复

1. Sandboxie Box 名不接受连字符，且 `Start.exe` 不会自动创建 Box。原实现的 `WeftBox-<run_id>` 会触发“无效的沙箱名参数”对话框并等待。现使用不超过 32 字符的合法唯一名称，并通过 `SbieIni.exe` 动态创建。
2. Git Bash 会把 `/wait`、`/silent` 改写为 Git 安装目录下的路径。诊断命令必须经 Python `subprocess` 或 PowerShell 原样传参；项目使用 Python，不受该转换影响。
3. `Start.exe` 不转发沙箱子进程 stdout/stderr。现由沙箱内包装进程写入输出文件，主机从对应沙箱目录读取。
4. 用户目录写入位于 `user\current\...`，不是 `drive\C\...`；输出读取和变更收集均已支持该映射。
5. 删除标记是零长度且创建时间固定为 `1986-05-23T15:47:02.250000Z` 的文件。收集器先识别删除标记，再比较内容哈希；当前 Run 的 `.runs` 内部产物不参与重命名检测。
6. 快速连续启动时可能出现 `0x40010004`。只有包装器未创建输出文件时才重试内部 helper；任意用户命令不自动重放。
7. `query *` 包含已禁用配置节，不能据此调用 `/terminate`；生命周期检查使用 `queryex /boxes *`。

## 越权写入的安全降级与验收

全盘 `ReadFilePath`，以及 `ClosedFilePath` + Root `NormalFilePath` + 运行时目录只读的组合，实测均使 Python/helper 无法正常启动。因此按 T0.2 预设的决策路径正式降级，不再宣称任意命令的 Root 外写入会被硬拒绝。

真实测试已验证：越权命令执行后真实目标不存在；外部变更标记 `protected`，审批 apply 整体拒绝；`audit_complete=false` 并保留明确警告。真实重命名、stale 冲突和显式覆盖也通过。当前未授权 helper 路径仍由应用层授权直接拒绝，普通写入由 Sandboxie 重定向。

该降级已同步 `docs/01-prd.md`、`docs/02-user-stories.md` 与 `docs/03-architecture.md`。不得把子进程退出码 0 或真实路径不变单独描述成硬拒绝。
