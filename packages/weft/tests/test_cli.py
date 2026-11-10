from __future__ import annotations

import socket
from types import SimpleNamespace
from typing import Any

import uvicorn
from weft.agent.settings import SettingsStore
from weft.cli import main


def test_version_command(capsys) -> None:
    """T0.1: the installed CLI reports the service version."""
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "weft 0.5.0"


def test_serve_gui_uses_webview2_without_opening_browser(monkeypatch) -> None:
    """US-SET-02/AC-4: serve --gui selects WebView2 instead of the browser."""

    class FakeSocket:
        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def bind(self, address: tuple[str, int]) -> None:
            return None

    application = SimpleNamespace(state=SimpleNamespace(session=SimpleNamespace(token="token")))
    calls: dict[str, Any] = {}
    monkeypatch.setattr(socket, "socket", lambda: FakeSocket())
    monkeypatch.setattr(
        SettingsStore,
        "read",
        lambda self: {"server": {"host": "127.0.0.1", "port": 7788}},
    )
    monkeypatch.setattr("weft.api.app.create_app", lambda **kwargs: application)
    monkeypatch.setattr(
        "weft.desktop.run_webview2",
        lambda app, host, port, token: calls.update(
            {"app": app, "host": host, "port": port, "token": token}
        ),
    )
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: False)
    monkeypatch.setattr("webbrowser.open", lambda url: False)

    assert main(["serve", "--gui"]) == 0
    assert calls == {
        "app": application,
        "host": "127.0.0.1",
        "port": 7788,
        "token": "token",
    }
