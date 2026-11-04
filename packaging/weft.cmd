@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT=%~dp0"
set "APP=%ROOT%app"
set "UV=%ROOT%tools\uv.exe"
set "PYTHON_VERSION=3.12"

if not exist "%APP%\VERSION" goto missing_files
if not exist "%UV%" goto missing_files
set /p WEFT_APP_VERSION=<"%APP%\VERSION"
if not defined LOCALAPPDATA goto no_local_app_data

set "WEFT_PORTABLE_ROOT=%ROOT%"
set "WEFT_UV_EXECUTABLE=%UV%"
set "WEFT_APP_ENV=%LOCALAPPDATA%\Weft\envs\%WEFT_APP_VERSION%"
set "UV_PROJECT_ENVIRONMENT=%WEFT_APP_ENV%"
set "UV_PYTHON_INSTALL_DIR=%LOCALAPPDATA%\Weft\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_CACHE_DIR=%LOCALAPPDATA%\Weft\cache"
set "UV_FIND_LINKS=%ROOT%wheels"
if not defined UV_PYTHON_DOWNLOADS set "UV_PYTHON_DOWNLOADS=automatic"
set "READY=%WEFT_APP_ENV%\.weft-ready"
set "BASE_PYTHON_FILE=%WEFT_APP_ENV%.base-python"
set "REINSTALL="

:options
if "%~1"=="" goto prepare
if "%~1"=="--version" goto version
if "%~1"=="--bootstrap-help" goto bootstrap_help
if "%~1"=="--repair" (
    set "WEFT_REPAIR=1"
    set "REINSTALL=--reinstall"
    shift
    goto options
)
if "%~1"=="--offline" (
    set "UV_OFFLINE=1"
    set "UV_PYTHON_DOWNLOADS=never"
    shift
    goto options
)
if "%~1"=="--china" (
    set "UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
    set "UV_PYTHON_INSTALL_MIRROR=https://gh-proxy.com/https://github.com/astral-sh/python-build-standalone/releases/download"
    shift
    goto options
)
if "%~1"=="--index-url" (
    if "%~2"=="" goto missing_option_value
    set "UV_INDEX_URL=%~2"
    shift
    shift
    goto options
)
if "%~1"=="--python-mirror" (
    if "%~2"=="" goto missing_option_value
    set "UV_PYTHON_INSTALL_MIRROR=%~2"
    shift
    shift
    goto options
)
goto collect_start

:collect_start
set "APP_ARGS="
:collect
if "%~1"=="" goto prepare
set "APP_ARGS=%APP_ARGS% "%~1""
shift
goto collect

:prepare
if defined WEFT_REPAIR goto install
if not exist "%WEFT_APP_ENV%\Scripts\weft.exe" goto install
if not exist "%READY%" goto install
if not exist "%BASE_PYTHON_FILE%" goto install
set /p WEFT_BASE_PYTHON=<"%BASE_PYTHON_FILE%"
if not exist "%WEFT_BASE_PYTHON%" goto install
goto launch

:install
echo Weft %WEFT_APP_VERSION%: preparing the application environment...
echo Python and dependencies are managed by uv under %LOCALAPPDATA%\Weft.
if exist "%WEFT_APP_ENV%" if not exist "%WEFT_APP_ENV%\Scripts\python.exe" rmdir /s /q "%WEFT_APP_ENV%"
if not exist "%LOCALAPPDATA%\Weft\envs" mkdir "%LOCALAPPDATA%\Weft\envs"
if errorlevel 1 goto failed

"%UV%" python install %PYTHON_VERSION% --no-bin --no-registry
if errorlevel 1 goto failed
"%UV%" python find %PYTHON_VERSION% --no-project > "%BASE_PYTHON_FILE%"
if errorlevel 1 goto failed
set /p WEFT_BASE_PYTHON=<"%BASE_PYTHON_FILE%"
if not exist "%WEFT_BASE_PYTHON%" goto failed

"%UV%" sync --project "%APP%" --frozen --python "%WEFT_BASE_PYTHON%" --no-install-project --no-progress %REINSTALL%
if errorlevel 1 goto failed
"%WEFT_APP_ENV%\Scripts\weft.exe" --version | "%SystemRoot%\System32\findstr.exe" /x /c:"weft %WEFT_APP_VERSION%" > nul
if errorlevel 1 goto failed
> "%READY%" echo %WEFT_APP_VERSION%
goto launch

:launch
set "UV_PYTHON=%WEFT_BASE_PYTHON%"
"%WEFT_APP_ENV%\Scripts\weft.exe" %APP_ARGS%
exit /b %ERRORLEVEL%

:version
echo weft %WEFT_APP_VERSION%
exit /b 0

:bootstrap_help
echo Weft bootstrap options (place before the application command):
echo   --china                 Use China mirrors for Python and packages
echo   --index-url URL         Use a custom Python package index
echo   --python-mirror URL     Use a custom uv Python download mirror
echo   --offline               Use only cached Python and packages
echo   --repair                Reinstall the application environment
echo   --version               Print the bundled Weft version without setup
echo.
echo Application commands: serve, run, pack, unpack, doctor
exit /b 0

:missing_option_value
echo Weft launcher: an option requires a value. 1>&2
exit /b 2

:missing_files
echo Weft launcher: app\VERSION or tools\uv.exe is missing. 1>&2
exit /b 2

:no_local_app_data
echo Weft launcher: LOCALAPPDATA is not defined. 1>&2
exit /b 2

:failed
echo Weft launcher: environment preparation failed. Check the output above and retry. 1>&2
exit /b 1
