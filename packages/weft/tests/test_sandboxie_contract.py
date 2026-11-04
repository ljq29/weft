from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from weft.sandbox.sandboxie import SandboxieSandbox


class FakeProcess:
    def __init__(self) -> None:
        self.pid = os.getpid()

    def poll(self) -> int:
        return 0


def test_sandboxie_start_command_environment_and_per_run_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-SBX-02/AC-1,2: valid dynamic box, safe environment and owned Run registration."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("USERNAME", "tester")
    calls: list[dict[str, Any]] = []
    config_calls: list[list[str]] = []

    def factory(command: list[str], **kwargs: Any) -> FakeProcess:
        calls.append({"command": command, **kwargs})
        return FakeProcess()

    def config_runner(command: list[str], **kwargs: Any) -> SimpleNamespace:
        config_calls.append(command)
        return SimpleNamespace(returncode=0, stderr=b"")

    first = SandboxieSandbox(
        tmp_path,
        "r-box-one",
        tmp_path / "Start.exe",
        tmp_path / "sandbox",
        process_factory=factory,
        config_runner=config_runner,
    )
    process = first.spawn(
        ["python", "-c", "print(1)"],
        tmp_path,
        {"WEFT_LLM_CONFIG": "default", "SECRET_KEY": "must-not-pass"},
        5,
    )
    command = calls[0]["command"]
    assert re.fullmatch(r"[A-Za-z0-9_]{1,32}", first.box)
    assert command[:4] == [
        str(tmp_path / "Start.exe"),
        f"/box:{first.box}",
        "/wait",
        "/silent",
    ]
    assert command[4] == "/env:WEFT_RUN_ID=r-box-one"
    spec = json.loads(Path(command[-3]).read_text(encoding="utf-8"))
    assert spec["cmd"] == ["python", "-c", "print(1)"]
    assert spec["env"]["WEFT_LLM_CONFIG"] == "default"
    assert "SECRET_KEY" not in spec["env"]
    assert ["set", first.box, "NetworkAccess", "*,Block"] == config_calls[1][1:]
    assert ["append", first.box, "NormalFilePath", str(tmp_path)] == config_calls[2][1:]
    record = json.loads(first.shared_registry_path.read_text(encoding="utf-8"))
    assert record["run_id"] == "r-box-one"
    assert record["owned_pids"][0]["pid"] == process.pid
    second = SandboxieSandbox(tmp_path, "r_box_two", tmp_path / "Start.exe")
    assert second.box != first.box
    process.close()
