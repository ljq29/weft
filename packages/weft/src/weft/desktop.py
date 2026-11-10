from __future__ import annotations

import os
import threading
import time
from typing import Any


class DesktopError(RuntimeError):
    pass


def webview2_version() -> str | None:
    if os.name != "nt":
        return None
    import winreg

    client = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    locations = (
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + client),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + client),
        (winreg.HKEY_CURRENT_USER, "Software\\" + client),
    )
    for root, path in locations:
        try:
            with winreg.OpenKey(root, path) as key:
                value, _ = winreg.QueryValueEx(key, "pv")
            if isinstance(value, str) and value:
                return value
        except OSError:
            continue
    return None


def run_webview2(application: Any, host: str, port: int, token: str) -> None:
    if os.name != "nt":
        raise DesktopError("WebView2 GUI 仅支持 Windows")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise DesktopError("WebView2 GUI 仅允许连接本机服务，请使用 127.0.0.1")
    try:
        import webview
    except ImportError as exception:
        raise DesktopError("缺少 pywebview，请重新安装 Weft 的 Windows 依赖") from exception
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(application, host=host, port=port, access_log=False))
    thread = threading.Thread(target=server.run, name="weft-service", daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive():
                raise DesktopError("本机服务未能启动，请检查端口和运行日志")
            if time.monotonic() >= deadline:
                raise DesktopError("本机服务启动超时")
            time.sleep(0.02)
        url = f"http://{host}:{port}/?token={token}"
        webview.create_window(
            "Weft",
            url,
            width=1440,
            height=900,
            min_size=(1080, 720),
        )
        try:
            webview.start(gui="edgechromium")
        except Exception as exception:
            raise DesktopError(
                f"WebView2 窗口启动失败：{exception}；请安装 Microsoft Edge WebView2 Runtime"
            ) from exception
    finally:
        server.should_exit = True
        thread.join(timeout=15)
    if thread.is_alive():
        raise DesktopError("WebView2 已关闭，但本机服务尚未退出，请检查运行日志")
