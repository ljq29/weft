from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from weft.agent.audit import AuditLog, TraceWriter
from weft.agent.loop import MaxTurnsExceeded, run_agent_loop
from weft.agent.tools import ToolDispatcher, ToolFailureLimitError
from weft.nodes.agent import AgentLoopNode
from weft_sdk import weft_ctx


class StubTool:
    def __init__(self, name: str = "lookup", failures: int = 0) -> None:
        self.name = name
        self.description = "Read test data"
        self.parameters = {"type": "object"}
        self.requires_confirmation = False
        self.lane = "trusted"
        self.failures = failures
        self.calls = 0

    def invoke(self, args: dict[str, Any]) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise ValueError("temporary failure")
        return json.dumps(args, ensure_ascii=False)


def call(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def test_agent_loop_tools_stop_priority_trace_and_redacted_audit(
    mock_llm: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-AGT-03/AC-1..5; US-AGT-10/AC-1..3; US-SBX-07/AC-1..3: ReAct audit."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path))
    mock_llm.scripts.extend(
        [
            {
                "text": "checking",
                "tool_calls": [
                    call(
                        "lookup",
                        {
                            "api_key": "raw-secret",
                            "url": "https://user:pw@example.test/?token=secret",
                        },
                    )
                ],
            },
            {"text": "DONE", "tool_calls": [call("lookup", {"unexpected": True}, "call_2")]},
        ]
    )
    from weft.agent.client import LLMClient
    from weft.agent.proxy import LLMProxy
    from weft.agent.settings import SettingsStore

    store = SettingsStore(tmp_path / "config.toml")
    store.update(
        {
            "llm": {
                "default": {
                    "base_url": mock_llm.base_url,
                    "api_key": "host-key",
                    "model": "mock",
                    "timeout": 3,
                }
            }
        }
    )
    tool = StubTool()
    deltas: list[str] = []
    events: list[tuple[str, dict[str, Any]]] = []
    usage: dict[str, int] = {}

    def record_usage(values: dict[str, int]) -> None:
        for key, value in values.items():
            usage[key] = usage.get(key, 0) + value

    with weft_ctx.activate(
        root=tmp_path,
        run_id="r_agent",
        node_id="n_agent",
        llm=LLMClient(LLMProxy(store)),
        stream=deltas.append,
        event=lambda name, data: events.append((name, data)),
        usage=record_usage,
    ):
        result = AgentLoopNode().execute(
            weft_ctx,
            {"tools": [tool]},
            {"llm": "default", "task": "lookup", "stop_on_text": "DONE"},
        )
    assert result["variable"] == {
        "final_text": "DONE",
        "turns": 2,
        "tool_calls_count": 1,
        "stopped_by": "stop_pattern",
        "partial": False,
    }
    assert tool.calls == 1
    assert deltas == ["checking", "DONE"]
    assert [name for name, _ in events] == [
        "node.llm_trace",
        "node.tool_call",
        "node.llm_trace",
    ]
    audit_text = (tmp_path / ".runs" / "r_agent" / "audit.jsonl").read_text(encoding="utf-8")
    audit = json.loads(audit_text)
    assert audit["status"] == "ok" and audit["args_redacted"]["api_key"] == "***"
    assert "raw-secret" not in audit_text and "token=secret" not in audit_text
    assert "user:pw" not in audit_text
    trace_text = (tmp_path / ".runs" / "r_agent" / "nodes" / "n_agent.trace.jsonl").read_text(
        encoding="utf-8"
    )
    assert "request_summary" in trace_text and "request_messages" not in trace_text
    assert "host-key" not in trace_text
    assert usage == {"prompt_tokens": 6, "completion_tokens": 2, "llm_calls": 2, "tool_calls": 1}


def test_duplicate_tools_fail_before_llm(tmp_path: Path) -> None:
    """US-AGT-03/AC-3: duplicate tool names are rejected before execution."""
    with pytest.raises(ValueError, match="Duplicate tool"):
        ToolDispatcher([StubTool(), StubTool()], AuditLog(tmp_path, "r_dup"), "n_agent")


def test_tool_errors_backfill_timeout_and_three_failures(tmp_path: Path) -> None:
    """US-AGT-03/AC-4: tool errors return to the loop until three consecutive failures."""
    tool = StubTool(failures=3)
    dispatcher = ToolDispatcher([tool], AuditLog(tmp_path, "r_error"), "n_agent")

    async def scenario() -> None:
        first = await dispatcher.invoke("lookup", {})
        assert first.status == "error" and "temporary failure" in first.text
        await dispatcher.invoke("lookup", {})
        with pytest.raises(ToolFailureLimitError):
            await dispatcher.invoke("lookup", {})

    asyncio.run(scenario())

    class SlowTool(StubTool):
        def invoke(self, args: dict[str, Any]) -> str:
            time.sleep(0.05)
            return "late"

    dispatcher = ToolDispatcher(
        [SlowTool("slow")], AuditLog(tmp_path, "r_timeout"), "n_agent", timeout=0.001
    )
    result = asyncio.run(dispatcher.invoke("slow", {}))
    assert result.status == "error" and "timed out" in result.text


def test_max_turns_default_failure_and_explicit_partial(tmp_path: Path) -> None:
    """US-AGT-03/AC-2: max_turns fails by default and only explicit partial returns."""
    from weft.agent.client import LLMResult

    class RepeatedLLM:
        async def chat(self, *args: Any, **kwargs: Any) -> LLMResult:
            result = LLMResult(
                {"role": "assistant", "content": "again"},
                "again",
                [call("lookup", {})],
                {},
            )
            return result

    async def scenario(on_max_turns: str) -> Any:
        return await run_agent_loop(
            llm=RepeatedLLM(),
            config_name="default",
            messages=[],
            dispatcher=ToolDispatcher([StubTool()], AuditLog(tmp_path, "r_turns"), "n_agent"),
            trace=TraceWriter(tmp_path, "r_turns", "n_agent"),
            max_turns=1,
            on_max_turns=on_max_turns,
        )

    with pytest.raises(MaxTurnsExceeded):
        asyncio.run(scenario("fail"))
    result = asyncio.run(scenario("return_partial"))
    assert result.partial is True and result.stopped_by == "max_turns"
