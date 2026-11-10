from __future__ import annotations

import sys
import time
from types import SimpleNamespace
from typing import Any

import pytest
import uvicorn
from weft.desktop import DesktopError, run_webview2


def test_webview2_uses_edge_backend_and_stops_service(monkeypatch) -> None:
    """US-SET-02/AC-4: the GUI hosts the same UI and closes its own service."""
    servers: list[Any] = []

    class FakeServer:
        def __init__(self, config: Any) -> None:
            self.config = config
            self.started = False
            self.should_exit = False
            servers.append(self)

        def run(self) -> None:
            self.started = True
            while not self.should_exit:
                time.sleep(0.005)

    calls: dict[str, Any] = {}

    def create_window(title: str, url: str, **options: Any) -> object:
        calls["title"] = title
        calls["url"] = url
        calls["options"] = options
        return object()

    def start(**options: Any) -> None:
        calls["start"] = options

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(create_window=create_window, start=start),
    )

    run_webview2(object(), "127.0.0.1", 7788, "secret-token")

    assert calls["title"] == "Weft"
    assert calls["url"] == "http://127.0.0.1:7788/?token=secret-token"
    assert calls["start"] == {"gui": "edgechromium"}
    assert servers[0].should_exit is True
    assert servers[0].config.host == "127.0.0.1"
    assert servers[0].config.port == 7788
    assert servers[0].config.access_log is False


def test_webview2_rejects_non_loopback_service() -> None:
    """US-SET-02/AC-4: desktop mode never wraps a non-loopback service."""
    with pytest.raises(DesktopError, match="仅允许连接本机服务"):
        run_webview2(object(), "0.0.0.0", 7788, "token")


def test_webview2_startup_failure_still_stops_service(monkeypatch) -> None:
    """US-SET-02/AC-4: a window startup failure does not leave a hidden service."""
    servers: list[Any] = []

    class FakeServer:
        def __init__(self, config: Any) -> None:
            self.started = False
            self.should_exit = False
            servers.append(self)

        def run(self) -> None:
            self.started = True
            while not self.should_exit:
                time.sleep(0.005)

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(
            create_window=lambda *args, **kwargs: object(),
            start=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("runtime missing")),
        ),
    )

    with pytest.raises(DesktopError, match="WebView2 窗口启动失败"):
        run_webview2(object(), "127.0.0.1", 7788, "token")
    assert servers[0].should_exit is True
