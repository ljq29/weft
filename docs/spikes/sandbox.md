# Sandboxie Windows 真机 Spike

## 当前实测环境与结果

- `C:\Program Files\Sandboxie-Plus\Start.exe` 存在，`SbieSvc` 正在运行。
- `weft doctor` 能发现 Sandboxie；这只证明可执行文件存在，不代表沙箱安全验收通过。
- 2026-11-04 实测 `Start.exe /box:<独立测试 box> /silent <cmd>` 不返回；加入 `/wait` 后同样不返回。
- 最小 `cmd /c exit 0` 与 Python `print(1)` 均复现；使用临时输出文件而非继承管道也不解决。
- `packages/weft/tests/test_sandboxie_real.py` 的真实 I/O、网络、COM 和生命周期用例因此在基础启动阶段失败，不能把这些失败解释为隔离能力已验证。

## 不得提前宣称的能力

动态 box 创建/删除/列举/终止、owned 进程树、写入重定向、删除标记、重命名、未知路径审计、默认拒绝网络、环回 LLMProxy 唯一例外、COM 拒绝和 stale apply 均仍需通过真实测试。

T0.2、T5.2、T5.4 及依赖它们的发布门禁保持未完成。不得用 NoneSandbox 或 Fake 进程结果代替上述真机结论。

## 后续排查

需要在可交互 Windows 桌面会话检查 Sandboxie 是否有等待用户确认的对话框、策略限制或损坏的安装状态，然后先让最小 `cmd /c exit 0` 正常退出，再重新运行 `uv run pytest packages/weft/tests/test_sandboxie_real.py -q`。不要为消除失败而终止用户已有 box 或放宽安全 AC。
