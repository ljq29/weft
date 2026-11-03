from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from weft.agent.audit import TraceWriter
from weft.agent.tools import ToolDispatcher


class MaxTurnsExceeded(RuntimeError):
    pass


@dataclass
class AgentResult:
    final_text: str
    turns: int
    tool_calls_count: int
    stopped_by: str
    partial: bool
    messages: list[dict[str, Any]]


async def run_agent_loop(
    *,
    llm: Any,
    config_name: str,
    messages: list[dict[str, Any]],
    dispatcher: ToolDispatcher,
    trace: TraceWriter,
    max_turns: int = 20,
    on_max_turns: str = "fail",
    stop_on_text: str = "",
    tool_choice: str = "auto",
    on_text: Any = None,
    on_turn: Any = None,
    record_usage: Any = None,
) -> AgentResult:
    final_text = ""
    count = 0
    turns = 0
    for turn in range(1, max_turns + 1):
        turns = turn
        started = time.perf_counter()
        result = await llm.chat(
            config_name,
            messages,
            tools=dispatcher.schemas(),
            tool_choice=tool_choice,
            on_text=on_text,
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        record = {
            "turn": turn,
            "request_summary": {
                "message_count": len(messages),
                "tools": list(dispatcher.tools),
            },
            "response": result.text,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "latency_ms": latency_ms,
        }
        if trace.include_prompts:
            record["request_messages"] = messages
        trace.append(**record)
        if on_turn is not None:
            on_turn(record)
        if record_usage is not None:
            record_usage(
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                llm_calls=1,
            )
        messages.append(result.message)
        final_text = result.text
        if stop_on_text and re.search(stop_on_text, result.text):
            return AgentResult(final_text, turns, count, "stop_pattern", False, messages)
        if not result.tool_calls:
            return AgentResult(final_text, turns, count, "assistant", False, messages)
        for call in result.tool_calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"])
                if not isinstance(args, dict):
                    raise ValueError("Tool arguments must be an object")
            except (json.JSONDecodeError, ValueError) as error:
                args = {"invalid_arguments": str(error)}
            dispatch = await dispatcher.invoke(name, args)
            count += 1
            if record_usage is not None:
                record_usage(tool_calls=1)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": name,
                    "content": dispatch.text,
                }
            )
            trace.append(
                turn=turn,
                tool=name,
                args_redacted=args,
                result_summary=dispatch.text[:500],
                duration_ms=dispatch.duration_ms,
                status=dispatch.status,
            )
    if on_max_turns == "return_partial":
        return AgentResult(final_text, turns, count, "max_turns", True, messages)
    raise MaxTurnsExceeded(f"Agent exceeded max_turns={max_turns}")
