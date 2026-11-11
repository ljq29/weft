# Agent Note: CMD 启动器与 uv 托管 Python 运行时

Status: implemented

## Problem

Nuitka standalone 主程序和内置完整 Python 各自携带 Polars、Arrow 与解释器文件，使绿色目录达到约 940 MiB、ZIP 约 292 MiB。完整复制宿主 Python 还混入文档、测试、Ruff 和第二个 uv。仅编译主服务不能消除这些重复，而工作流隔离、ExcelWorker 和 Sandboxie helper 仍需要真实 Python。

## Decision

发布物只提供 `weft-<version>-windows-x64.zip`，不保留无版本号兼容副本。ZIP 根目录只包含 `weft.cmd`；README、许可证、`bootstrap-index.ps1`、内置 uv、三个同版本 wheel、生产 `pyproject.toml`/`uv.lock` 和带 SHA-256 的 manifest 统一位于 `runtime/`，不包含 Python、Nuitka 主程序或预建 venv。构建目录仍使用 `dist/weft-windows-x64/`，但 ZIP 内不套这一外层目录。`weft.cmd` 与 `weft.portable` 均从 `runtime/` 定位 uv、wheel 和应用项目，避免启动与工作流环境使用不同路径契约。Weft 以普通 wheel 纯 Python 运行，不为启动器引入 Rust 或其他编译工具链；源选择只依赖 Windows 10/11 自带的 Windows PowerShell。

`weft.cmd` 在首次执行应用命令时调用内置 uv，把托管 CPython 3.12、缓存和版本化应用环境安装到 `%LOCALAPPDATA%/Weft`。uv 使用 `only-managed`，不依赖宿主 Python、PATH 或注册表。生产项目把三个 Weft 包都声明为直接依赖，确保 `tool.uv.sources` 对本地 wheel 生效；业务环境不包含开发依赖。

应用主服务、ExcelWorker、Sandboxie helper 和 doctor 使用应用 venv 的 `sys.executable`。工作流环境继续使用各自 `<root>/.venv`，但 `UV_PYTHON` 指向启动器记录的托管 base Python，禁止把应用 venv 当作工作流宿主或依赖来源。启动器通过环境变量传递发布根目录，不再从 `sys.executable` 推断它。

`--china` 和自定义镜像参数只影响 bootstrap；`--offline` 禁止联网并复用缓存，`--repair` 重装当前应用环境。未通过 `--china` 或 `--index-url` 显式指定包源的联网安装，由 `bootstrap-index.ps1` 提供 PyPI 官方、已配置且检测可用的 pip 源、清华源、强制已有源四项菜单；已有源可用时默认使用它，否则默认官方源。普通探测失败输出 HTTP 状态或最内层异常，菜单第 4 项与 `--force-configured-index` 跳过探测，后者同时跳过交互；强制模式只把探测判断交给用户，实际下载仍由 uv 决定成败。

助手读取 `PIP_INDEX_URL`、`UV_INDEX_URL`、`PIP_CONFIG_FILE` 与标准 pip 配置，菜单和诊断隐藏 URL 凭据；HTTP 内网主机通过 `UV_INSECURE_HOST` 显式允许，uv 使用 Windows 证书存储。选择结果只在安装期间经临时文件传回 CMD，读取后立即删除。显式包源参数和离线模式不提示，避免无人值守安装阻塞。`bootstrap-index.ps1` 必须保留 UTF-8 BOM，否则 Windows PowerShell 5.1 会按 ANSI 误读中文并产生解析错误；源码测试和便携 manifest 验收都检查该字节前缀。

安装成功且版本检查通过后才写 ready 标记，后续启动直接执行应用 venv 中的 `weft.exe`。`--version` 不触发下载。首次没有缓存时必须联网，离线模式不承诺凭空生成环境。包源菜单不改变托管 CPython 的下载地址，隔离网络仍需 `--python-mirror` 或已有 uv 缓存。

## Alternatives considered

1. **继续使用 Nuitka standalone/onefile**：能减少散装 Python 文件，但主程序与真实解释器仍重复携带原生依赖，onefile 还增加自解压和子进程路径复杂度，因此放弃。
2. **用 Rust 编写原生启动器**：能提供单个 EXE 入口，但项目技术栈没有 Rust，为几十行进程引导增加编译工具链不值得，因此采用 Windows 已有 CMD。
3. **下载预建 `.venv`**：看似省去安装，却受 `pyvenv.cfg`、入口启动器和绝对路径约束，因此只下载 Python、wheel 和锁文件，在目标机创建环境。
4. **发布零散 `.py` 文件**：更直接，但包数据、版本、入口点和哈希管理较弱，因此保留纯 Python wheel。
5. **把所有 Python 与第三方 wheel 都打入离线 ZIP**：首次完全离线，但会恢复大产物和多平台 wheelhouse 维护；当前提供缓存离线，首次下载仍需网络。

## Consequences

收益是发布 ZIP 保持轻量（0.5.2 实测约 22 MB），构建不再需要 Nuitka，主服务与 helper 共用一份应用依赖，uv 缓存还能供工作流环境复用；内网用户可直接复用已经配置的 pip 源，不必另外理解 uv 配置。代价是首次启动需要下载、等待安装并可能进行一次源选择，CMD 父进程需要随应用生命周期存在，进程树清理必须包含其子 Python；离线能力取决于本机缓存，代码签名和 SmartScreen 信誉仍需独立处理。源可用性探测只证明 HTTP 端点可访问，最终依赖解析仍以 uv sync 为准。

## Verification

- `packages/weft/tests/test_portable.py` 覆盖应用 Python、托管 base Python、内置 uv、缓存和开发环境路径选择。
- `packages/weft/tests/test_portable_bootstrap.py` 以本地 HTTP 服务覆盖可用 pip 配置源、探测 HTTP 错误、菜单与命令行强制源、官方与清华选择、HTTP 主机参数和 UTF-8 BOM；七项集成测试通过。
- 构建烟测已确认目录约 60 MiB、Release ZIP 为 15,259,248 字节，`weft.cmd --version` 与 `--bootstrap-help` 可直接执行。
- `scripts/verify_portable.py` 使用独立 `%LOCALAPPDATA%` 和仅 System32 的 PATH，校验版本化 ZIP 根目录、manifest 与脚本 BOM、首次托管 Python/依赖下载、真实 CSV、缓存离线重跑与 `--repair`、鉴权服务与前端，并清理 CMD/Python 进程树。0.5.2 验收通过真实菜单选择 `PIP_INDEX_URL` 中的清华源；后续强制源改动已通过 `--force-configured-index --repair` 无交互真实安装及后续离线工作流验收。`runtime/` 布局改动已用版本化 ZIP 在含空格路径下真实解压，并完成上述全部验收。
- 184 项单元测试、36 项集成测试、23 项前端测试和 11 项 Playwright E2E 通过；12 项真实 Excel/Sandboxie `win_real` 测试通过，托管 Python 下 `doctor --json` 为 `fail_count=0`。
- CI 与 Release 均执行同一启动器验收，不能只检查版本输出或 wheel import。

## 记录审计

新决策完全取代原 Nuitka 运行时方案；本篇接管其真实 Python 隔离、内部 helper、发布验收和备选理由，[标签发布流程](../process/2026-11-04-tag-driven-github-release.md) 的入站链接已改到本篇，旧 Nuitka 笔记已删除。Windows-only 验证和 Sandboxie 外写遏制记录不受影响。
