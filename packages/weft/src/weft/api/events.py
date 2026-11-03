from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self.subscribers: list[
            tuple[
                asyncio.Queue[dict[str, Any]],
                Callable[[dict[str, Any]], bool],
                asyncio.AbstractEventLoop,
            ]
        ] = []

    def subscribe(
        self, matches: Callable[[dict[str, Any]], bool]
    ) -> tuple[asyncio.Queue[dict[str, Any]], asyncio.AbstractEventLoop]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        self.subscribers.append((queue, matches, loop))
        return queue, loop

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers = [item for item in self.subscribers if item[0] is not queue]

    def publish(self, event: dict[str, Any]) -> None:
        for queue, matches, loop in list(self.subscribers):
            if matches(event):
                loop.call_soon_threadsafe(queue.put_nowait, event)
