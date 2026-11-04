# Sandboxie Windows 真机 Spike

## 当前实测环境与结果

- Sandboxie-Plus `5.72.5` 位于 `C:\Program Files\Sandboxie-Plus`，`SbieDrv` 与 `SbieSvc` 正在运行。
- 2026-11-04 已修复最小启动：合法且已创建的 Box 中，`cmd /c exit 0` 和 Python `print(1)` 均正常退出。
- `uv run pytest packages/weft/tests/test_sandboxie_real.py -q`：3 项真实测试通过，覆盖 helper 读写、创建/删除审计、未授权 helper 路径拒绝、默认外网阻断、环回代理例外、COM 拒绝及跨 Run 清理。
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

## 仍未完成的安全验收

T0.2、T5.2、T5.4 暂不因上述修复自动勾完成。任意 spawn 对 Root 外的硬拒绝、未知变化完整性、stale apply 冲突及真实 Pi 场景仍需按任务卡验收。全盘 `ReadFilePath` 实测会使 Python/helper 无法正常启动，不能把它当作已经可用的写保护方案。

当前未授权 helper 路径由应用层授权拦截，普通写入由 Sandboxie 重定向；这与“任意沙箱命令对 Root 外写入均被硬拒绝”不是同一结论。不得用 NoneSandbox、Fake 或本次基础测试代替剩余安全 AC。
