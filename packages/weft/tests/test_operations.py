from __future__ import annotations

import asyncio
import json
import socket
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from weft.agent.settings import LLMConfigError, SettingsStore
from weft.api.app import create_app
from weft.api.security import Session, load_session
from weft.cli import main
from weft.doctor import run_doctor
from weft.engine import Engine
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument


def test_settings_defaults_merge_validation_and_key_preservation(tmp_path: Path) -> None:
    """US-SET-01/AC-1,2,3: defaults, validation and updates preserve user settings."""
    store = SettingsStore(tmp_path / "config.toml")
    settings = store.read()
    assert settings["server"]["host"] == "127.0.0.1"
    assert settings["excel"]["call_timeout"] == 60
    assert settings["trigger"]["http_wait_timeout_s"] == 300
    text = store.path.read_text(encoding="utf-8")
    assert "# Weft user settings" in text
    for section in (
        "server",
        "sandbox",
        "sandbox.sandboxie",
        "excel",
        "agent",
        "trigger",
        "logging",
        "cache",
    ):
        assert f"[{section}]" in text
    assert "[llm.default]" in text
    store.update(
        {
            "llm": {
                "default": {
                    "base_url": "http://localhost",
                    "model": "test",
                    "api_key": "{{SECRET_18zl8jzs}}",
                }
            },
            "cache": {"run_retention": 12},
        }
    )
    updated = store.update({"server": {"port": 7790}, "logging": {"level": "DEBUG"}})
    assert updated["cache"]["run_retention"] == 12
    assert store.llm("default")["api_key"] == "{{SECRET_18zl8jzs}}"
    assert updated["llm"]["default"]["api_key"] == "***"
    with pytest.raises(LLMConfigError, match="trigger.http_wait_timeout_s"):
        store.update({"trigger": {"http_wait_timeout_s": 0}})
    with pytest.raises(LLMConfigError, match="unknown"):
        store.update({"unknown": True})


def test_service_logging_trace_ids_and_run_log_correlation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-SET-03/AC-1,2,3: JSON service logs and Run logs share trace_id without secrets."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    SettingsStore().update({"logging": {"level": "DEBUG", "retention_days": 14}})
    from weft.operations import configure_service_logging, log_excel_call, log_http, log_llm_request

    configure_service_logging(SettingsStore().read())
    log_http("GET", "/api/system/version", 200, "trace-service")
    log_excel_call("read_range", "trace-excel")
    log_llm_request("default", "HTTP", "chat/completions")
    files = list((tmp_path / "config" / "logs").glob("weft-*.log"))
    assert len(files) == 1
    entries = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert entries[0]["record"]["extra"]["trace_id"] == "trace-service"
    assert any("Excel COM call summary" in item["record"]["message"] for item in entries)
    assert any("LLM request summary" in item["record"]["message"] for item in entries)
    assert "api_key" not in files[0].read_text(encoding="utf-8")

    root = tmp_path / "trace.weft"
    root.mkdir()
    document = WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "trace",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": [
                {
                    "id": "n_00000001",
                    "type": "flow.trigger",
                    "node_version": 1,
                    "name": "Trigger",
                    "position": {"x": 0, "y": 0},
                    "params": {},
                }
            ],
        }
    )
    engine = Engine()
    record = asyncio.run(engine.run(engine.prepare(document, root, builtin_registry())))
    meta = json.loads((root / ".runs" / record.run_id / "meta.json").read_text(encoding="utf-8"))
    logs = [
        json.loads(line)
        for line in (root / ".runs" / record.run_id / "log.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert meta["trace_id"] == record.run_id
    assert all(item["trace_id"] == record.run_id for item in logs)


def test_trace_retention_and_api_doctor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """US-SET-03/AC-3; US-SET-04/AC-2: trace retention and doctor JSON are available."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    from weft.agent.audit import TraceWriter

    path = tmp_path / ".runs" / "r_20260101_000000_0000" / "nodes" / "n_00000001.trace.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")
    old = time.time() - 8 * 86400
    import os

    os.utime(path, (old, old))
    TraceWriter.cleanup(tmp_path, 7)
    assert not path.exists()
    app = create_app(
        enable_triggers=False,
        session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"),
    )
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        response = client.get("/api/system/doctor", headers={"Authorization": "Bearer test"})
        assert response.status_code == 200
        assert response.json()["checks"]


def test_cli_help_and_port_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """US-SET-02/AC-3; US-SET-04/AC-1: help lists commands and occupied port hints --port."""
    with pytest.raises(SystemExit) as help_exit:
        main(["--help"])
    assert help_exit.value.code == 0
    output = capsys.readouterr().out
    for command in ("serve", "run", "pack", "unpack", "doctor"):
        assert command in output
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
        assert main(["serve", "--no-browser", "--port", str(port)]) == 1
    assert "--port" in capsys.readouterr().out


@pytest.mark.integration
def test_real_serve_readiness_session_and_doctor(tmp_path: Path) -> None:
    """US-SET-02/AC-1; US-SET-04/AC-1,2: real service is ready and doctor reports checks."""
    import subprocess
    import sys

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    port = 7899
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))
    process = subprocess.Popen(
        [sys.executable, "-m", "weft", "serve", "--no-browser", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=dict(__import__("os").environ),
    )
    try:
        started = time.perf_counter()
        for _ in range(500):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=0.1
                ) as response:
                    assert response.status == 200
                    break
            except OSError:
                time.sleep(0.02)
        else:
            raise AssertionError("service did not start")
        print(f"service_start_seconds={time.perf_counter() - started:.3f}")
        session = load_session()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/system/version",
            headers={"Authorization": f"Bearer {session.token}"},
        )
        with urllib.request.urlopen(request, timeout=1) as response:
            assert json.loads(response.read())["version"] == "0.5.0"
        report = run_doctor(settings=SettingsStore(tmp_path / "config" / "config.toml"))
        assert {item["name"] for item in report["checks"]} == {
            "python",
            "uv",
            "excel",
            "sandboxie",
            "pi",
            "webview2",
            "port",
            "appdata",
        }
        assert report["fail_count"] == sum(item["status"] == "FAIL" for item in report["checks"])
    finally:
        process.terminate()
        process.wait(timeout=10)
        monkeypatch.undo()


def test_chat_memory_and_run_retention_are_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-SET-03/AC-4: chat/memory age policies and Run count cleanup stay independent."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    from weft.agent.memory import MemoryStore
    from weft.triggers.chat import ChatSessionStore
    from weft.workflow.history import RunHistory

    root = tmp_path / "retention.weft"
    for kind in ("chat", "memory"):
        path = root / ".runs" / kind / "s_old.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        old = time.time() - 31 * 86400
        import os

        os.utime(path, (old, old))
    for day in (1, 2):
        path = root / ".runs" / f"r_2026010{day}_000000_0000"
        path.mkdir(parents=True)
        (path / "meta.json").write_text("{}", encoding="utf-8")
    store = SettingsStore()
    store.update(
        {
            "cache": {
                "run_retention": 1,
                "chat_retention_days": 0,
                "memory_retention_days": 0,
            }
        }
    )
    ChatSessionStore(root).cleanup()
    MemoryStore(root).cleanup()
    RunHistory(root).cleanup(1)
    assert (root / ".runs" / "chat" / "s_old.jsonl").exists()
    assert (root / ".runs" / "memory" / "s_old.jsonl").exists()
    assert len(list(root.glob(".runs/r_*"))) == 1
    store.update({"cache": {"chat_retention_days": 30, "memory_retention_days": 30}})
    ChatSessionStore(root).cleanup()
    MemoryStore(root).cleanup()
    assert not (root / ".runs" / "chat" / "s_old.jsonl").exists()
    assert not (root / ".runs" / "memory" / "s_old.jsonl").exists()


def test_doctor_cleanup_uses_only_owned_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-SET-04/AC-3: doctor cleanup dispatches only registered Excel/sandbox records."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    registry = tmp_path / "config" / "sandbox-runs" / "r_owned.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"run_id": "r_owned"}), encoding="utf-8")
    from weft.sandbox.sandboxie import SandboxieSandbox

    monkeypatch.setattr(
        SandboxieSandbox, "cleanup_run", classmethod(lambda cls, run_id: run_id == "r_owned")
    )
    import os

    if os.name == "nt":
        from weft.excel.xlwings_backend import OwnedProcessRegistry

        monkeypatch.setattr(OwnedProcessRegistry, "cleanup", lambda self: [4321])
        monkeypatch.setattr(OwnedProcessRegistry, "remove", lambda self, pid: None)
    from weft.doctor import _cleanup

    messages = _cleanup()
    if os.name == "nt":
        assert any("4321" in message for message in messages)
    assert any("r_owned" in message for message in messages)
