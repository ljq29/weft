from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from weft.api.app import create_app
from weft.api.security import Session
from weft.triggers.chat import ChatSessionStore


def document(with_llm: bool = False) -> dict[str, Any]:
    nodes = [
        {
            "id": "n_00000001",
            "type": "flow.trigger",
            "node_version": 1,
            "name": "Trigger",
            "position": {"x": 0, "y": 0},
            "params": {"chat": {"enabled": True}},
        }
    ]
    edges = []
    if with_llm:
        nodes.append(
            {
                "id": "n_00000002",
                "type": "agent.llm_call",
                "node_version": 1,
                "name": "LLM",
                "position": {"x": 0, "y": 0},
                "params": {"llm": "default", "user_prompt": "Reply"},
            }
        )
        edges.append(
            {
                "id": "e_00000001",
                "source": "n_00000001",
                "sourcePort": "message",
                "target": "n_00000002",
                "targetPort": "message",
                "order": 0,
            }
        )
    nodes.append(
        {
            "id": "n_00000003",
            "type": "flow.chat_output",
            "node_version": 1,
            "name": "Chat Output",
            "position": {"x": 0, "y": 0},
            "params": {},
        }
    )
    edges.append(
        {
            "id": "e_00000002",
            "source": "n_00000002" if with_llm else "n_00000001",
            "sourcePort": "message",
            "target": "n_00000003",
            "targetPort": "message",
            "order": 0,
        }
    )
    return {
        "schema_version": 1,
        "revision": 1,
        "id": "wf_cc10000001",
        "name": "chat-test",
        "created_at": "2026-01-01T00:00:00+00:00",
        "modified_at": "2026-01-01T00:00:00+00:00",
        "nodes": nodes,
        "edges": edges,
    }


def wait(client: TestClient, run_id: str) -> dict[str, Any]:
    for _ in range(100):
        record = client.get(f"/api/runs/{run_id}").json()
        if record["status"] in {"succeeded", "failed", "cancelled"}:
            return record
        time.sleep(0.02)
    raise AssertionError("Chat run did not finish")


def test_chat_rest_run_session_history_and_clear(tmp_path: Path) -> None:
    """US-AGT-07/AC-1,2,4; US-TRG-03/AC-1,2: REST chat creates a unified Run."""
    root = tmp_path / "chat.weft"
    root.mkdir()
    (root / "workflow.json").write_text(json.dumps(document()), encoding="utf-8")
    app = create_app(session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"))
    app.state.roots["wf_cc10000001"] = root
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        client.headers["Authorization"] = "Bearer test"
        response = client.post(
            "/api/workflows/wf_cc10000001/chat",
            json={"message": "你好", "session_id": "s_test"},
        )
        assert response.status_code == 202
        result = response.json()
        assert result["session_id"] == "s_test"
        record = wait(client, result["run_id"])
        trigger = record["trigger"]
        assert trigger["source"] == "chat"
        assert trigger["payload"] == {"message": "你好", "history_len": 0}
        assert record["nodes"]["n_00000001"]["outputs"]["message"]["inline"] == [
            {"role": "user", "content": "你好"}
        ]
        history = client.get("/api/workflows/wf_cc10000001/chat/s_test").json()
        assert [item["role"] for item in history] == ["user", "assistant"]
        assert history[-1]["content"] == "你好"
        assert history[-1]["streaming"] is False
        second = client.post(
            "/api/workflows/wf_cc10000001/chat",
            json={"message": "再次", "session_id": "s_test"},
        ).json()
        second_record = wait(client, second["run_id"])
        assert second_record["trigger"]["payload"]["history_len"] == 2
        client.post("/api/workflows/wf_cc10000001/chat/s_test/clear", json={"clear_memory": False})
        assert client.get("/api/workflows/wf_cc10000001/chat/s_test").json() == []


def test_chat_disabled_is_explicit(tmp_path: Path) -> None:
    """US-TRG-03/AC-2: disabled chat returns CHAT_DISABLED instead of starting a Run."""
    value = document()
    value["nodes"][0]["params"] = {"chat": {"enabled": False}}
    root = tmp_path / "disabled.weft"
    root.mkdir()
    (root / "workflow.json").write_text(json.dumps(value), encoding="utf-8")
    app = create_app(session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"))
    app.state.roots[value["id"]] = root
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        response = client.post(
            f"/api/workflows/{value['id']}/chat",
            json={"message": "test"},
            headers={"Authorization": "Bearer test"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CHAT_DISABLED"


def test_chat_stream_and_final_share_message_identity(
    tmp_path: Path, monkeypatch: Any, mock_llm: Any
) -> None:
    """US-AGT-07/AC-3,5: streamed text and final Chat Output replace one message."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path))
    from weft.agent.settings import SettingsStore

    SettingsStore().update(
        {
            "llm": {
                "default": {
                    "base_url": mock_llm.base_url,
                    "api_key": "",
                    "model": "mock",
                    "timeout": 3,
                }
            }
        }
    )
    mock_llm.scripts.append({"chunks": ["Hel", "lo"]})
    root = tmp_path / "stream.weft"
    root.mkdir()
    (root / "workflow.json").write_text(json.dumps(document(True)), encoding="utf-8")
    app = create_app(session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"))
    app.state.roots["wf_cc10000001"] = root
    events: list[dict[str, Any]] = []
    original_sink = app.state.engine.event_sink
    app.state.engine.event_sink = lambda event: (events.append(event), original_sink(event))
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        client.headers["Authorization"] = "Bearer test"
        response = client.post(
            "/api/workflows/wf_cc10000001/chat",
            json={"message": "hello", "session_id": "s_stream"},
        )
        result = response.json()
        record = wait(client, result["run_id"])
        assert record["status"] == "succeeded"
        history = client.get("/api/workflows/wf_cc10000001/chat/s_stream").json()
    streams = [event for event in events if event["event"] == "node.stream"]
    final = next(event for event in events if event["event"] == "chat.message")
    assert [event["data"]["delta"] for event in streams] == ["Hel", "lo"]
    assert all(
        event["data"]["chat_links"][0]["message_id"] == final["data"]["message_id"]
        for event in streams
    )
    assert [item["role"] for item in history].count("assistant") == 1
    assert history[-1]["content"] == "Hello"


def test_chat_retention_zero_disables_cleanup(tmp_path: Path, monkeypatch: Any) -> None:
    """US-AGT-07/AC-4: retention 0 preserves old UI sessions."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path))
    from weft.agent.settings import SettingsStore

    SettingsStore().update({"cache": {"chat_retention_days": 0}})
    store = ChatSessionStore(tmp_path)
    store.append({"session_id": "s_old", "content": "old"})
    path = tmp_path / ".runs" / "chat" / "s_old.jsonl"
    old = time.time() - 40 * 86400
    os.utime(path, (old, old))
    store.cleanup()
    assert path.exists()
