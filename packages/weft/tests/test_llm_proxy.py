from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from weft.agent.client import LLMClient, LLMHTTPError
from weft.agent.proxy import LLMProxy
from weft.agent.settings import LLMConfigError, SettingsStore
from weft.api.app import create_app
from weft.api.security import Session


def config(store: SettingsStore, mock: Any, suffix: str = "/v1/") -> None:
    store.update(
        {
            "llm": {
                "default": {
                    "base_url": mock.base_url + suffix,
                    "api_key": "sk-test-secret",
                    "model": "mock-model",
                    "extra_headers": {"X-Test": "weft"},
                    "timeout": 3,
                }
            }
        }
    )


def test_settings_api_masks_and_preserves_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_llm: Any
) -> None:
    """US-AGT-01/AC-1,2,3: settings CRUD masks keys and tests the named endpoint."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path))
    store = SettingsStore()
    config(store, mock_llm, suffix="")
    app = create_app(session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"))
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        client.headers["Authorization"] = "Bearer test"
        response = client.get("/api/settings")
        assert response.status_code == 200
        settings = response.json()
        assert settings["llm"]["default"]["api_key"] == "***"
        assert "sk-test-secret" not in str(settings)
        settings["llm"]["default"]["model"] = "changed"
        updated = client.put("/api/settings", json=settings).json()
        assert updated["llm"]["default"]["model"] == "changed"
        assert store.llm("default")["api_key"] == "sk-test-secret"
        result = client.post("/api/settings/llm/default/test")
        assert result.status_code == 200 and result.json()["ok"] is True
        assert mock_llm.requests[-1]["path"] == "/v1/models"
        with pytest.raises(LLMConfigError, match="LLM config 'missing' not found"):
            store.llm("missing")


@pytest.mark.integration
@pytest.mark.anyio
async def test_openai_client_stream_auth_retry_and_error_body(
    mock_llm: Any, tmp_path: Path
) -> None:
    """US-AGT-01/AC-4; US-AGT-02/AC-5: OpenAI paths, retries and HTTP errors are explicit."""
    store = SettingsStore(tmp_path / "config.toml")
    config(store, mock_llm)
    mock_llm.scripts.extend(
        [
            {"status": 429, "body": {"error": "rate limited"}},
            {"chunks": ["WEFT_", "OK"], "usage": {"prompt_tokens": 8, "completion_tokens": 2}},
            {"status": 400, "body": {"error": "bad request body"}},
        ]
    )
    client = LLMClient(LLMProxy(store))
    deltas: list[str] = []
    result = await client.chat(
        "default", [{"role": "user", "content": "test"}], temperature=0.2, on_text=deltas.append
    )
    assert result.text == "WEFT_OK"
    assert result.usage == {"prompt_tokens": 8, "completion_tokens": 2}
    assert deltas == ["WEFT_", "OK"]
    request = mock_llm.requests[-1]
    assert request["path"] == "/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer sk-test-secret"
    assert request["headers"]["X-Test"] == "weft"
    assert request["body"]["model"] == "mock-model"
    assert request["body"]["stream"] is True
    assert "sk-test-secret" not in str(result)
    with pytest.raises(LLMHTTPError, match="bad request body") as error:
        await client.chat("default", [])
    assert error.value.status == 400
