# T0.3 Excel / xlwings 真机 Spike

## 结论

本次真机结果支持既定架构：Excel 多实例必须按稳定目标或由用户明确选择，不能假设 `GetActiveObject` 返回最近活动实例；独立 ExcelWorker 在模态调用超时后仍被占用，需要监督重建；跨宿主 `Local\WeftExcelCOM` 可以串行化 COM 临界区；owned 实例可按 PID、进程创建时间、Run 与心跳记录识别和清理。

无需修改现有多实例、超时或 owned 生命周期 AC。逐格写明显慢于批量写，正式实现必须使用整块 Range 读写。模拟并发编辑不等同于人工鼠标操作体验，视觉无闪烁、不抢焦点仍在 M3 人工验收。

## 环境与原始数据

- 日期：2026-11-03（UTC 原始时间见报告）
- OS：Microsoft Windows 11 专业工作站版，10.0.26300
- CPU：13th Gen Intel Core i5-13600KF；RAM：63.8 GiB
- Excel：16.0；Python：3.12.10；xlwings：0.37.8；pywin32：312
- 脚本：`scripts/spikes/excel.py`
- 命令：`uv run python scripts/spikes/excel.py`
- 原始报告：`.test-reports/excel-spike.json`（忽略提交，运行后生成）
- 最终 Run：`spike-58a8fbf5`，脚本状态 `passed`，退出后无 EXCEL 进程残留

## 实测结果

|项目|结果|
| --- | --- |
|多实例与 GetActiveObject|创建 owned PID 33420、32496；`GetActiveObject` 返回先创建的 33420，不是后创建的 32496，不能据此猜测“最近活动”实例|
|稳定目标|两个工作簿保存为不同文件名后可唯一匹配；最近选择在测试用用户级 `excel-targets.toml` 中往返成功|
|可见写回与并发编辑|可见实例整块写入成功；另一次 COM 赋值模拟外部编辑后读取为 43.0|
|模态与真超时|实际 `Application.InputBox` 调用在 0.5 s 后超时；原 Worker 仍忙，后续两个排队调用均在 0.2 s 后超时|
|Worker 重建|终止旧 Worker 后，新 Worker 新请求成功；超时请求未自动重放|
|owned 清理|旧 Worker 的 Excel 仅在 PID + 创建时间 + Run 匹配后终止；常规实例退出无清理失败|
|跨宿主互斥|两个独立 Worker 的 COM 临界区分别为 466301.5117591–466301.8126911 与 466301.8127012–466302.1157395，无重叠|

## 受控基准

以下为同机单次 spike 结果，不是其他硬件的通用验收承诺。

|操作|耗时|
| --- | ---: |
|1000 × 100（10 万单元格）整块写入|0.125653 s|
|1000 × 100（10 万单元格）整块读取|0.034456 s|
|1000 次逐格写入|6.596435 s|
|1000 单元格一次批量写入|0.008819 s|

逐格写未达到 PRD 中 1000 次 `< 2 s` 的受控优化目标；该目标不作为任意机器的硬 AC，但进一步说明正式后端应避免逐格 COM 往返。

## M3 正式后端复测

`test_excel_real.py` 已验证独立 Worker 中的隐藏实例、工作簿、批量读写、append、原子更新、工作表管理、显式保存与 owned 清理，并验证可见实例 attach、fast_mode 状态恢复和日期序列号转换。新实例统一由 Weft 登记，退出使用实际进程状态检查；可见实例不由 Run 自动关闭。

2026-11-04 正式后端在同一基准机连续运行 3 次，1000 × 100 整块写入（含 Arrow 转换和 IPC）分别为 0.800365、0.785330、0.820741 秒，整块读取分别为 0.131778、0.121366、0.119818 秒，均低于 3 秒目标。原始报告为 `.test-reports/excel-backend-benchmark-run1.json` 至 `run3.json`，每次测试后 EXCEL 进程均为 0。早期 6.999940 秒结果仅作历史基线，不再代表当前实现。

## T7.7 Macro 与 visible owned 清理复测

2026-11-04 使用 xlwings 官方 BSD-3-Clause 测试夹具 `packages/weft/tests/fixtures/macro-book.xlsm`，真实 `Application.Run` 调用 `Module1.Test1("Test1a", "Test1b")` 返回 `1`；缺失宏仍返回可读 COM 错误。两项 `win_real` 测试通过。

另修复显式 `close_app(..., "discard")` 在 visible owned 实例退出卡住时跳过清理的问题：现在仅在 PID 与创建时间匹配时终止该 owned 实例。定向单元测试、真实 visible attach 和场景 A 均通过，测试结束后 EXCEL 进程数为 0。Run 的默认 release 仍不自动关闭 visible 实例。
