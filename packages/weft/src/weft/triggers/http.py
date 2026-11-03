from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weft.agent.settings import SettingsStore


class HttpTriggerDisabledError(ValueError):
    pass


class HttpRateLimiter:
    def __init__(self) -> None:
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    def failed(self, ip: str) -> bool:
        now = time.monotonic()
        entries = self.failures[ip]
        while entries and now - entries[0] >= 60:
            entries.popleft()
        entries.append(now)
        return len(entries) > 10


class HttpSource:
    def __init__(self, coordinator: Any) -> None:
        self.coordinator = coordinator
        self.limiter = HttpRateLimiter()

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def trigger(
        self,
        workflow: Any,
        root: Path,
        registry: Any,
        body: Any,
        token: str,
        ip: str,
        wait: bool = False,
    ) -> dict[str, Any]:
        trigger = next(node for node in workflow.nodes if node.type == "flow.trigger")
        http = trigger.params.get("http", {})
        if not http.get("enabled"):
            raise HttpTriggerDisabledError("HTTP trigger is disabled")
        valid = bool(token) and secrets.compare_digest(
            self.token_hash(token), http.get("token_hash", "")
        )
        if not valid:
            if self.limiter.failed(ip):
                raise PermissionError("Too many failed HTTP trigger attempts")
            raise PermissionError("Invalid HTTP trigger token")
        from weft.triggers.preflight import precheck_excel_targets

        await precheck_excel_targets(workflow, self.coordinator.engine)
        result = await self.coordinator.submit(
            workflow,
            root,
            registry,
            trigger={
                "source": "http",
                "ts": datetime.now(UTC).isoformat(),
                "payload": {"body": body},
            },
        )
        if result.disposition == "dropped" or result.run_id is None:
            return {"run_id": None, "disposition": "dropped"}
        response: dict[str, Any] = {
            "run_id": result.run_id,
            "disposition": result.disposition,
        }
        if not wait:
            return response
        settings = SettingsStore().read().get("trigger", {})
        timeout = settings.get("http_wait_timeout_s", 300)
        try:
            await asyncio.wait_for(self.coordinator.wait(result.run_id), timeout)
        except TimeoutError:
            record = self.coordinator.engine.runs[result.run_id].record
            response.update({"status": record.status, "outputs": {}, "wait_timed_out": True})
            return response
        record = self.coordinator.engine.runs[result.run_id].record
        response["status"] = record.status
        response["outputs"] = self.coordinator.engine.http_responses.get(result.run_id, {})
        return response
