from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from weft.nodes.registry import builtin_registry
from weft.worker import WorkerPool, WorkflowEnvironment
from weft_sdk import ToolCapability, weft_ctx
from weft_worker.shell import cmd_literal, powershell_literal, render_command

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def execute(root: Path, command: str, shell: str, **params: object) -> tuple[dict, list[str]]:
    logs: list[str] = []
    with weft_ctx.activate(
        root=root,
        run_id="r_shell",
        variables={"message": params.pop("value", "hello")},
        log=lambda level, message: logs.append(message),
    ):
        result = (
            builtin_registry()
            .get("code.shell")
            .execute(weft_ctx, {}, {"command": command, "shell": shell, **params})
        )
    return result, logs


@pytest.mark.integration
def test_powershell_literal_metacharacters_and_newline(tmp_path: Path) -> None:
    """US-TBL-09/AC-1,2: PowerShell interpolation preserves metacharacters literally."""
    value = "space ' \"\n$ ` % & | >"
    result, logs = execute(tmp_path, "Write-Output {message}", "powershell", value=value)
    assert result["variable"]["stdout"] == value
    assert result["variable"]["exit_code"] == 0
    assert logs == value.splitlines()
    assert powershell_literal("'") == "''''"
    with pytest.raises(ValueError):
        powershell_literal("bad\0value")


@pytest.mark.integration
def test_cmd_literal_metacharacters_and_unsafe_values(tmp_path: Path) -> None:
    """US-TBL-09/AC-1,2: cmd uses independent quoting and rejects unsafe literals."""
    value = "space ' $ ` & | >"
    result, _ = execute(tmp_path, "echo {message}", "cmd", value=value)
    assert result["variable"]["stdout"] == f'"{value}"'
    assert cmd_literal("a&b") == '"a&b"'
    for unsafe in ('double"quote', "%PATH%", "line\nbreak"):
        with pytest.raises(ValueError):
            cmd_literal(unsafe)
    with pytest.raises(ValueError, match="变量不存在"):
        render_command("echo {missing}", {}, "cmd")


@pytest.mark.integration
def test_shell_nonzero_and_fail_policy(tmp_path: Path) -> None:
    """US-TBL-09/AC-1: exit codes are returned or fail according to policy."""
    result, _ = execute(tmp_path, "exit 3", "powershell", fail_on_nonzero=False)
    assert result["variable"]["exit_code"] == 3
    with pytest.raises(RuntimeError, match="退出码 3"):
        execute(tmp_path, "exit 3", "powershell")


@pytest.mark.integration
def test_shell_worker_streams_logs_in_real_time(tmp_path: Path) -> None:
    """US-TBL-09/AC-3: Worker log notifications arrive before process completion."""
    (tmp_path / "nodes").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        f'''[project]
name = "shell-test"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = ["weft-worker==0.0.0"]
[tool.uv.sources]
weft-worker = {{ path = "{(PROJECT_ROOT / "packages/weft-worker").as_posix()}" }}
weft-sdk = {{ path = "{(PROJECT_ROOT / "packages/weft-sdk").as_posix()}" }}
''',
        encoding="utf-8",
    )
    environment = WorkflowEnvironment(tmp_path)
    environment.sync()
    pool = WorkerPool(environment, "r_shell_stream", size=1)
    events: list[tuple[float, str]] = []
    pool.on_log = lambda node_id, level, message: events.append((time.monotonic(), message))
    try:
        result = asyncio.run(
            pool.execute(
                "n_shell",
                "code.shell",
                {
                    "command": (
                        "Write-Output 'first'; Start-Sleep -Milliseconds 200; Write-Output 'second'"
                    ),
                    "shell": "powershell",
                },
                {},
            )
        )
        assert "error" not in result
        assert [message for _, message in events] == ["first", "second"]
        assert events[1][0] - events[0][0] >= 0.15
        assert pool.process_ids
    finally:
        pool.close()
    assert builtin_registry().get("code.shell").tool_capability == ToolCapability.NONE
