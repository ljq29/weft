from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from weft.agent.audit import AuditLog
from weft.agent.confirmation import ConfirmationManager
from weft.agent.pi import PiRunner
from weft.agent.proxy import LLMProxy
from weft.agent.proxy_server import LocalLLMProxyServer
from weft.agent.sandbox_tools import SandboxedTool, SandboxManager
from weft.agent.settings import SettingsStore
from weft.agent.tools import ToolDispatcher
from weft.nodes.agent import PiAgentNode, SandboxedToolsNode
from weft_sdk import weft_ctx


def settings(tmp_path: Path) -> SettingsStore:
    store = SettingsStore(tmp_path / "config.toml")
    store.update({"sandbox": {"default": "none", "allow_none_sandbox": True}})
    return store


def test_sandboxed_tools_none_function_and_bash_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-AGT-05/AC-1,2,4,6: none exposes only controlled shadow file tools."""
    store = settings(tmp_path)
    with weft_ctx.activate(root=tmp_path, run_id="r_tools"):
        monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path))
        result = SandboxedToolsNode().execute(
            weft_ctx,
            {},
            {"tools": ["read", "write", "edit", "list"], "sandbox": "none"},
        )
        with pytest.raises(ValueError, match="bash requires sandboxie"):
            SandboxedToolsNode().execute(weft_ctx, {}, {"tools": ["bash"], "sandbox": "none"})
    prepared = SimpleNamespace(root=tmp_path, record=SimpleNamespace(run_id="r_tools"))
    manager = SandboxManager(store)

    async def approve(request: dict[str, Any]) -> dict[str, Any]:
        return {"approved": True, "args": request["args"]}

    manager.confirmation_handler = approve
    tools = [manager.create(prepared, item, "n_agent") for item in result["tools"]]
    tools[1].requires_confirmation = False
    tools[1].invoke({"path": "note.txt", "content": "hello"})
    assert tools[0].invoke({"path": "note.txt"}) == "hello"
    tools[2].invoke({"path": "note.txt", "old_string": "hello", "new_string": "edited"})
    assert not (tmp_path / "note.txt").exists()
    assert "note.txt" in tools[3].invoke({"path": "."})
    audit = AuditLog(tmp_path, "r_tools")
    dispatcher = ToolDispatcher([tools[2]], audit, "n_agent")
    dispatch = asyncio.run(
        dispatcher.invoke(
            "edit", {"path": "note.txt", "old_string": "edited", "new_string": "done"}
        )
    )
    assert dispatch.status == "ok"
    assert audit.path.exists()


def test_sandboxed_tool_confirmation_modifies_args_and_rejects(tmp_path: Path) -> None:
    """US-AGT-12/AC-1,2: approval can modify args; rejection performs no write."""
    store = settings(tmp_path)
    manager = SandboxManager(store)
    prepared = SimpleNamespace(root=tmp_path, record=SimpleNamespace(run_id="r_confirm"))

    async def approve(request: dict[str, Any]) -> dict[str, Any]:
        return {"approved": True, "args": {**request["args"], "path": "approved.txt"}}

    manager.confirmation_handler = approve
    tool = manager.create(
        prepared,
        {
            "name": "write",
            "binding": {"sandbox": "none", "cwd": str(tmp_path)},
        },
        "n_agent",
    )
    assert tool.requires_confirmation is True
    tool.invoke({"path": "original.txt", "content": "safe"})
    assert not (tmp_path / "original.txt").exists()
    assert not (tmp_path / "approved.txt").exists()

    async def reject(request: dict[str, Any]) -> dict[str, Any]:
        return {"approved": False, "args": request["args"]}

    manager.confirmation_handler = reject
    rejected = manager.create(
        prepared,
        {"name": "write", "binding": {"sandbox": "none", "cwd": str(tmp_path)}},
        "n_agent",
    )
    dispatch = asyncio.run(
        ToolDispatcher([rejected], AuditLog(tmp_path, "r_confirm"), "n_agent").invoke(
            "write", {"path": "never.txt", "content": "no"}
        )
    )
    assert dispatch.status == "rejected"
    assert not (tmp_path / "never.txt").exists()


def test_confirmation_manager_waiting_modified_args_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-AGT-12/AC-2,3: waiting state, modified args and timeout rejection are explicit."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path))
    events: list[dict[str, Any]] = []
    prepared = SimpleNamespace(record=SimpleNamespace(status="running", run_id="r_wait"))
    manager = ConfirmationManager(SimpleNamespace(_event=lambda *args: events.append(args)))

    async def approved() -> None:
        task = asyncio.create_task(
            manager.request(
                prepared, {"node_id": "n_agent", "tool": "write", "args": {"path": "a"}}
            )
        )
        await asyncio.sleep(0)
        request_id = next(iter(manager.pending))
        assert prepared.record.status == "waiting"
        assert manager.resolve(request_id, "approve", {"path": "b"}) is True
        result = await task
        assert result["args"] == {"path": "b"}

    asyncio.run(approved())
    assert prepared.record.status == "running"
    assert events[0][1] == "node.confirm_request"
    SettingsStore(tmp_path / "config.toml").update({"agent": {"confirm_timeout_s": 0.01}})

    async def expires() -> None:
        result = await manager.request(
            prepared, {"node_id": "n_agent", "tool": "write", "args": {}}
        )
        assert result["approved"] is False and result["reason"] == "timeout"

    asyncio.run(expires())


def test_bash_output_is_truncated(tmp_path: Path) -> None:
    """US-AGT-05/AC-5: bash output has a bounded length and an explicit truncation marker."""

    class Process:
        def wait(self, timeout: float) -> int:
            return 0

        def output(self) -> tuple[bytes, bytes]:
            return b"x" * 100, b""

    class FakeSandbox:
        def spawn(self, *args: Any) -> Process:
            return Process()

    result = SandboxedTool("bash", FakeSandbox(), tmp_path, max_output_chars=10).invoke(
        {"command": "safe"}
    )
    assert "x" * 10 in result and "...[truncated]" in result


def test_pi_requires_sandboxie_and_command_is_noninteractive(tmp_path: Path) -> None:
    """US-AGT-06/AC-1,3,6: pi cannot run outside Sandboxie and uses fixed safe flags."""
    with weft_ctx.activate(root=tmp_path, run_id="r_pi"):
        with pytest.raises(ValueError, match="Pi Agent requires sandboxie"):
            PiAgentNode().execute(
                weft_ctx, {}, {"task": "test", "llm": "default", "sandbox": "none"}
            )
    runner = PiRunner(tmp_path, "r_pi")
    command = runner.command("pi", "model", "task", [])
    for flag in ("--print", "--no-tools", "--no-extensions", "--no-mcp", "--no-session"):
        assert flag in command
    assert command[-1] == "task"
    with pytest.raises(FileNotFoundError, match="not installed"):
        runner.run(
            task="task",
            cwd=tmp_path,
            pi_path=str(tmp_path / "missing-pi"),
            llm="default",
            sandbox=object(),
            timeout=1,
            extra_args=[],
        )


def test_loopback_proxy_adds_host_key_without_exposing_it(mock_llm: Any, tmp_path: Path) -> None:
    """US-AGT-06/AC-4: the host proxy injects credentials outside the child boundary."""
    store = SettingsStore(tmp_path / "config.toml")
    store.update(
        {
            "llm": {
                "default": {
                    "base_url": mock_llm.base_url,
                    "api_key": "raw-host-key",
                    "model": "mock",
                    "timeout": 3,
                }
            }
        }
    )
    proxy = LocalLLMProxyServer(LLMProxy(store))
    proxy.start()
    try:
        request = urllib.request.Request(
            f"{proxy.url}/v1/default/chat/completions",
            data=json.dumps({"messages": []}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            body = response.read().decode()
        assert mock_llm.requests[-1]["headers"]["Authorization"] == "Bearer raw-host-key"
        assert "raw-host-key" not in body
    finally:
        proxy.close()


@pytest.mark.win_real
def test_real_pi_uses_sandboxie_cwd_stream_and_host_proxy(tmp_path: Path, mock_llm: Any) -> None:
    """US-AGT-06/AC-2,4: real Pi runs in Sandboxie with streamed output and no raw key."""
    import shutil

    from weft.sandbox.base import create_sandbox

    pi_path = shutil.which("pi") or ""
    assert pi_path and Path(pi_path).is_file()
    root = tmp_path / "pi-root"
    root.mkdir()
    store = SettingsStore(tmp_path / "config.toml")
    store.update(
        {
            "sandbox": {"default": "sandboxie"},
            "llm": {
                "default": {
                    "base_url": mock_llm.base_url,
                    "api_key": "raw-host-key",
                    "model": "mock",
                    "timeout": 3,
                }
            },
        }
    )
    run_id = "r_pi_win_real"
    sandbox = create_sandbox(root, run_id, "sandboxie", store)
    try:
        result = PiRunner(root, run_id, store).run(
            task="Reply with exactly WEFT_MOCK_OK and nothing else.",
            cwd=root,
            pi_path=pi_path,
            llm="default",
            sandbox=sandbox,
            timeout=60,
            extra_args=[],
        )
        assert result["exit_code"] == 0
        assert result["final_text"] == "WEFT_MOCK_OK"
        assert result["trajectory"]
        specs = list((root / ".runs" / run_id).glob("process-*.json"))
        assert specs
        assert all(
            json.loads(path.read_text(encoding="utf-8"))["cwd"] == str(root) for path in specs
        )
        artifacts = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in (root / ".runs" / run_id).rglob("*")
            if path.is_file()
        )
        assert "raw-host-key" not in artifacts
    finally:
        sandbox.discard()
