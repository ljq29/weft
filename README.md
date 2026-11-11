# Weft

Weft 是本地优先的可视化工作流工具：以 KNIME 式表格数据流编排 CSV、Excel、LLM/Agent 和文件处理，并提供触发器、运行历史、沙箱变更审批及可移植打包。

## 环境与安装

### Windows 轻量目录版

下载并解压 `weft-windows-x64.zip`，运行其中的 `weft.cmd`。目录只包含启动器、源选择助手、uv、生产依赖锁和同版本 wheel，不含 Python 或 Nuitka 主程序。首次执行应用命令时，启动器通过 uv 在 `%LOCALAPPDATA%/Weft` 下载托管 CPython 3.12、创建版本化应用环境并安装锁定依赖，无需预装 Python 或 uv。

```bat
weft.cmd serve
weft.cmd serve --gui
weft.cmd --china serve
weft.cmd --offline serve
weft.cmd --repair serve
weft.cmd --bootstrap-help
```

- 首次安装或 `--repair` 且未显式指定包源时，启动器提示选择：1）PyPI 官方源；2）已配置且连通性检测可用的 pip 源；3）清华大学镜像源。已有源可用时默认选择它，否则默认官方源。
- 已有源从 `PIP_INDEX_URL`、`UV_INDEX_URL`、`PIP_CONFIG_FILE` 及标准 pip 配置文件读取；显示地址时隐藏凭据。内网 HTTP 源会为主机启用 uv 的显式允许配置，TLS 使用 Windows 证书存储。
- `--china` 使用清华 PyPI 源，并通过 `gh-proxy.com` 下载 python-build-standalone；`--index-url` 和 `--python-mirror` 可分别自定义包与 Python 下载镜像。`--china` 和 `--index-url` 跳过源选择，适用于无人值守安装。
- `--offline` 只使用已缓存的 Python 和包，不显示源选择；首次从未安装过的机器不能离线 bootstrap。
- 应用环境按版本隔离，升级不会覆盖旧环境；`--repair` 强制重装当前版本。
- pip 源选择只影响 Python 包下载；托管 CPython 仍使用 uv 默认地址或 `--python-mirror` 指定的镜像。
- Excel、Sandboxie-Plus 和可选的 Node.js/pi 仍需单独安装。

### 开发与 wheel 安装

- Windows 10/11（v1 的真实 Excel 与 Sandboxie 目标平台）
- Python >= 3.12、uv、Node.js 22 与 pnpm
- 可选：Microsoft Excel、Sandboxie-Plus、pi

开发环境使用中国镜像：

```bash
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uv sync
pnpm install --registry=https://registry.npmmirror.com
```

启动完整应用：

```bash
pnpm -C frontend build
uv run weft serve
```

服务默认仅监听 `127.0.0.1:7788`，自动打开带随机会话令牌的同源 URL。令牌同时保存在仅当前用户可读的会话文件中；不要分享该 URL 或会话文件。

需要桌面窗口时使用 `weft serve --gui`（便携版为 `weft.cmd serve --gui`）。该模式通过 pywebview 调用 Microsoft Edge WebView2 Runtime，打开同一套 UI；关闭窗口会停止本次服务。`--gui` 仅允许环回地址，不改变 REST/WS、鉴权或工作流执行语义。WebView2 Runtime 缺失时可先使用浏览器模式，并通过 `weft doctor` 检查。

常用 CLI：

```bash
uv run weft run path/to/demo.weft --wait
uv run weft pack path/to/demo.weft
uv run weft unpack demo.weft.zip -d D:/flows
uv run weft doctor --json
uv run weft doctor --cleanup
```

监听非本机地址前必须配置 `server.global_token`。服务配置位于 `%APPDATA%/weft/config.toml`，原始 LLM key 不写入工作流或打包文件。

## 功能范围

- DAG 工作流、循环、Metanode、变量、分类缓存和独立 Worker pool
- 表格、文件、Excel、Rule Engine 和可信 Worker Shell Command
- LLM Call、Agent Loop、授权 NodeTool、聊天与 Memory 会话
- 手动、聊天、定时、文件与 HTTP 触发
- 沙箱工具、变更 diff/审批、运行历史和保留清理
- 打包预检、密钥扫描、zip slip 防护和依赖同步导入

## 测试与构建

```bash
uv run poe check
uv run pytest -m integration
pnpm -C e2e test
pnpm -C frontend build
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uv build --wheel --out-dir dist packages/weft-sdk
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uv build --wheel --out-dir dist packages/weft-worker
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uv build --wheel --out-dir dist packages/weft
uv run python scripts/build_portable.py --skip-frontend-build --skip-wheel-build
uv run python scripts/verify_portable.py
```

`docs/01-prd.md` 是需求入口，`docs/07-roadmap.md` 记录任务及真实验收状态，`docs/08-testing-strategy.md` 定义测试与安全门禁。

## 当前验收边界

- 项目仅支持 Windows，不支持 WSL/Linux；Fake 结果不能替代真实 Excel、Sandboxie 或真实模型验收。
- Sandboxie 独立 box、网络拒绝、进程归属和真实 Excel 宏已成功通过 `win_real` 验证。
- 跨机交接要求兼容 Weft/uv、锁定依赖及声明的外部资源在目标机可用。
- 当前发布版本为 `0.5.2`；完整 v1 的人工交接与采用门禁仍在 roadmap 的 `T7.10` 跟踪。

## License

Weft 使用 [MIT License](LICENSE)。Excel、Sandboxie-Plus、Node.js 等外部依赖遵循各自许可证。
