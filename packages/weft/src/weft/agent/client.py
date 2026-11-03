from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from weft.agent.proxy import LLMProxy


class LLMHTTPError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"LLM HTTP {status}: {body[:4000]}")
        self.status = status
        self.body = body


@dataclass
class LLMResult:
    message: dict[str, Any]
    text: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, int]

    @property
    def prompt_tokens(self) -> int:
        return self.usage.get("prompt_tokens", 0)

    @property
    def completion_tokens(self) -> int:
        return self.usage.get("completion_tokens", 0)


class LLMClient:
    def __init__(self, proxy: LLMProxy) -> None:
        self.proxy = proxy

    async def chat(
        self,
        name: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        on_text: Callable[[str], None] | None = None,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        for attempt in range(3):
            async with self.proxy.stream(name, payload) as response:
                if response.status_code >= 400:
                    body = response.text
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < 2:
                            await asyncio.sleep(0.25 * 2**attempt)
                            continue
                    raise LLMHTTPError(response.status_code, body)
                return await self._read_stream(response, on_text)
        raise AssertionError("unreachable")

    async def _read_stream(self, response: Any, on_text: Callable[[str], None] | None) -> LLMResult:
        text = ""
        calls: dict[int, dict[str, Any]] = {}
        usage: dict[str, int] = {}
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            if event.get("usage"):
                usage = event["usage"]
            for choice in event.get("choices", []):
                delta = choice.get("delta", {})
                content = delta.get("content")
                if content:
                    text += content
                    if on_text is not None:
                        on_text(content)
                for part in delta.get("tool_calls", []):
                    index = part.get("index", 0)
                    call = calls.setdefault(
                        index,
                        {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        },
                    )
                    call["id"] += part.get("id", "")
                    function = part.get("function", {})
                    call["function"]["name"] += function.get("name", "")
                    call["function"]["arguments"] += function.get("arguments", "")
        message: dict[str, Any] = {"role": "assistant", "content": text}
        tool_calls = [calls[index] for index in sorted(calls)]
        if tool_calls:
            message["tool_calls"] = tool_calls
        return LLMResult(message, text, tool_calls, usage)
