from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

import jsonschema

from weft.agent.audit import AuditLog, redact


class ToolProtocol(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]
    requires_confirmation: bool
    lane: str

    def invoke(self, args: dict[str, Any]) -> str | Awaitable[str]: ...


class ToolFailureLimitError(RuntimeError):
    pass


@dataclass
class ToolDispatchResult:
    text: str
    status: str
    duration_ms: int


class ToolDispatcher:
    def __init__(
        self,
        tools: list[ToolProtocol],
        audit: AuditLog,
        node_id: str,
        timeout: float = 120,
        on_call: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.tools = {tool.name: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise ValueError("Duplicate tool names are not allowed")
        self.audit = audit
        self.node_id = node_id
        self.timeout = timeout
        self.on_call = on_call
        self.failures: dict[str, int] = {}

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.tools.values()
        ]

    async def invoke(self, name: str, args: dict[str, Any]) -> ToolDispatchResult:
        started = time.perf_counter()
        status = "ok"
        try:
            tool = self.tools[name]
            jsonschema.validate(args, tool.parameters)
            async with asyncio.timeout(self.timeout):
                result = await asyncio.to_thread(tool.invoke, args)
                if inspect.isawaitable(result):
                    result = await result
            text = str(result)
            self.failures.pop(name, None)
            return self._finish(name, args, status, started, text)
        except Exception as error:
            status = "error"
            self.failures[name] = self.failures.get(name, 0) + 1
            detail = (
                f"Tool timed out after {self.timeout}s"
                if isinstance(error, TimeoutError)
                else str(error)
            )
            text = f"Tool error: {detail}"
            self._finish(name, args, status, started, text)
            if self.failures[name] >= 3:
                raise ToolFailureLimitError(f"Tool '{name}' failed 3 consecutive times") from error
            return ToolDispatchResult(text, status, self._elapsed(started))

    def _finish(
        self, name: str, args: dict[str, Any], status: str, started: float, text: str
    ) -> ToolDispatchResult:
        duration = self._elapsed(started)
        lane = getattr(self.tools.get(name), "lane", "trusted")
        self.audit.append(
            node_id=self.node_id,
            tool=name,
            args=args,
            status=status,
            duration_ms=duration,
            result=text,
            lane=lane,
        )
        if self.on_call is not None:
            self.on_call(
                {
                    "tool": name,
                    "args_redacted": redact(args),
                    "result_summary": text[:500],
                    "duration_ms": duration,
                    "status": status,
                }
            )
        return ToolDispatchResult(text, status, duration)

    @staticmethod
    def _elapsed(started: float) -> int:
        return round((time.perf_counter() - started) * 1000)
