from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from weft.agent.settings import SettingsStore


class LLMProxy:
    def __init__(self, settings: SettingsStore) -> None:
        self.settings = settings

    def _target(
        self, name: str, endpoint: str, config: dict[str, Any]
    ) -> tuple[str, dict[str, str]]:
        from weft.operations import log_llm_request

        log_llm_request(name, "HTTP", endpoint)
        base = config["base_url"].rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        headers = dict(config.get("extra_headers", {}))
        if config.get("api_key"):
            headers["Authorization"] = f"Bearer {config['api_key']}"
        else:
            headers.pop("Authorization", None)
        headers["Content-Type"] = "application/json"
        return f"{base}/{endpoint}", headers

    async def request(
        self, name: str, method: str, endpoint: str, payload: dict[str, Any] | None = None
    ) -> httpx.Response:
        return await self._request(name, self.settings.llm(name), method, endpoint, payload)

    async def _request(
        self,
        name: str,
        config: dict[str, Any],
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url, headers = self._target(name, endpoint, config)
        if payload is not None and endpoint == "chat/completions":
            payload.setdefault("model", config["model"])
        async with httpx.AsyncClient(timeout=config.get("timeout", 120)) as client:
            return await client.request(method, url, json=payload, headers=headers)

    @asynccontextmanager
    async def stream(self, name: str, payload: dict[str, Any]) -> AsyncIterator[httpx.Response]:
        config = self.settings.llm(name)
        url, headers = self._target(name, "chat/completions", config)
        payload.setdefault("model", config["model"])
        async with httpx.AsyncClient(timeout=config.get("timeout", 120)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    await response.aread()
                yield response

    async def test(self, name: str) -> dict[str, Any]:
        return await self._test(name, self.settings.llm(name))

    async def test_draft(self, name: str, config: dict[str, Any]) -> dict[str, Any]:
        return await self._test(name, config)

    async def _test(self, name: str, config: dict[str, Any]) -> dict[str, Any]:
        response = await self._request(name, config, "GET", "models")
        body = response.text[:4000]
        api_key = config.get("api_key", "")
        if api_key:
            body = body.replace(api_key, "***")
        if response.status_code >= 400:
            raise RuntimeError(f"LLM connection failed ({response.status_code}): {body}")
        try:
            data = response.json()
        except ValueError as exception:
            raise RuntimeError("LLM connection returned invalid JSON") from exception
        models = data.get("data", []) if isinstance(data, dict) else []
        return {"ok": True, "models": models if isinstance(models, list) else []}
