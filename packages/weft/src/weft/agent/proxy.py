from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from weft.agent.settings import SettingsStore


class LLMProxy:
    def __init__(self, settings: SettingsStore) -> None:
        self.settings = settings

    def _target(self, name: str, endpoint: str) -> tuple[dict[str, Any], str, dict[str, str]]:
        config = self.settings.llm(name)
        base = config["base_url"].rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        headers = dict(config.get("extra_headers", {}))
        if config.get("api_key"):
            headers["Authorization"] = f"Bearer {config['api_key']}"
        else:
            headers.pop("Authorization", None)
        headers["Content-Type"] = "application/json"
        return config, f"{base}/{endpoint}", headers

    async def request(
        self, name: str, method: str, endpoint: str, payload: dict[str, Any] | None = None
    ) -> httpx.Response:
        config, url, headers = self._target(name, endpoint)
        if payload is not None and endpoint == "chat/completions":
            payload.setdefault("model", config["model"])
        async with httpx.AsyncClient(timeout=config.get("timeout", 120)) as client:
            return await client.request(method, url, json=payload, headers=headers)

    @asynccontextmanager
    async def stream(self, name: str, payload: dict[str, Any]) -> AsyncIterator[httpx.Response]:
        config, url, headers = self._target(name, "chat/completions")
        payload.setdefault("model", config["model"])
        async with httpx.AsyncClient(timeout=config.get("timeout", 120)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    await response.aread()
                yield response

    async def test(self, name: str) -> dict[str, Any]:
        response = await self.request(name, "GET", "models")
        body = response.text[:4000]
        if response.status_code >= 400:
            raise RuntimeError(f"LLM connection failed ({response.status_code}): {body}")
        data = response.json()
        return {"ok": True, "models": data.get("data", []) if isinstance(data, dict) else []}
