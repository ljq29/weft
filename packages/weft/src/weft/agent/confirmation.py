from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from weft.agent.settings import SettingsStore


@dataclass
class PendingConfirmation:
    request_id: str
    future: asyncio.Future[dict[str, Any]]
    run_id: str
    node_id: str
    tool: str
    args: dict[str, Any]


class ConfirmationManager:
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.pending: dict[str, PendingConfirmation] = {}

    async def request(self, prepared: Any, request: dict[str, Any]) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        pending = PendingConfirmation(
            request_id,
            future,
            prepared.record.run_id,
            request["node_id"],
            request["tool"],
            request["args"],
        )
        self.pending[request_id] = pending
        settings = SettingsStore().read().get("agent", {})
        timeout = settings.get("confirm_timeout_s", 600)
        prepared.record.status = "waiting"
        self.engine._event(
            prepared,
            "node.confirm_request",
            request["node_id"],
            {
                "request_id": request_id,
                "run_id": prepared.record.run_id,
                "tool": request["tool"],
                "args": request["args"],
                "timeout_at": (datetime.now(UTC) + timedelta(seconds=timeout)).isoformat(),
            },
        )
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            future.cancel()
            return {"approved": False, "args": request["args"], "reason": "timeout"}
        finally:
            self.pending.pop(request_id, None)
            if prepared.record.status == "waiting":
                prepared.record.status = "running"
            self.engine._event(
                prepared,
                "node.confirm_resolved",
                request["node_id"],
                {"request_id": request_id},
            )

    def resolve(
        self, request_id: str, decision: str, modified_args: dict[str, Any] | None = None
    ) -> bool:
        pending = self.pending.get(request_id)
        if pending is None:
            return False
        args = modified_args if modified_args is not None else pending.args
        pending.future.set_result({"approved": decision == "approve", "args": args})
        return True
