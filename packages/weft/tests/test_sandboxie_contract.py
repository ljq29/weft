from __future__ import annotations

import json
import os
from pathlib import Path
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
    """T5.2 (contract only): Start.exe args and owned Run registration; not win_real."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("USERNAME", "tester")
    calls: list[dict[str, Any]] = []

    def factory(command: list[str], **kwargs: Any) -> FakeProcess:
        calls.append({"command": command, **kwargs})
        return FakeProcess()

    first = SandboxieSandbox(
        tmp_path,
        "r_box_one",
        tmp_path / "Start.exe",
        tmp_path / "sandbox",
        process_factory=factory,
    )
    process = first.spawn(
        ["python", "-c", "print(1)"],
        tmp_path,
        {"WEFT_LLM_CONFIG": "default", "SECRET_KEY": "must-not-pass"},
        5,
    )
    command = calls[0]["command"]
    assert command[:4] == [
        str(tmp_path / "Start.exe"),
        "/box:WeftBox-r_box_one",
        "/wait",
        "/silent",
    ]
    assert command[4] == "/env:WEFT_RUN_ID=r_box_one"
    assert command[-3:] == ["python", "-c", "print(1)"]
    assert calls[0]["env"]["WEFT_LLM_CONFIG"] == "default"
    assert "SECRET_KEY" not in calls[0]["env"]
    record = json.loads(first.shared_registry_path.read_text(encoding="utf-8"))
    assert record["run_id"] == "r_box_one"
    assert record["owned_pids"][0]["pid"] == process.pid
    second = SandboxieSandbox(tmp_path, "r_box_two", tmp_path / "Start.exe")
    assert second.box != first.box
    process.close()
