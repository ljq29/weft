from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from weft.agent.settings import SettingsStore
from weft.api.app import create_app
from weft.api.security import Session
from weft.engine import Engine, RunCoordinator
from weft.nodes.registry import builtin_registry
from weft.triggers.http import HttpSource
from weft.triggers.manager import TriggerManager, validate_trigger_config
from weft.triggers.preflight import precheck_excel_targets
from weft.workflow import WorkflowDocument, WorkflowStore


def document(
    trigger: dict[str, Any], response: bool = False, wait: bool = False
) -> WorkflowDocument:
    nodes = [
        {
            "id": "n_00000001",
            "type": "flow.trigger",
            "node_version": 1,
            "name": "Trigger",
            "position": {"x": 0, "y": 0},
            "params": trigger,
        }
    ]
    edges = []
    if response:
        nodes.append(
            {
                "id": "n_00000002",
                "type": "flow.http_response",
                "node_version": 1,
                "name": "Response",
                "position": {"x": 0, "y": 0},
                "params": {"status_code": 201, "body": {"ok": True}},
            }
        )
    if wait:
        nodes.append(
            {
                "id": "n_00000003",
                "type": "flow.wait",
                "node_version": 1,
                "name": "Wait",
                "position": {"x": 0, "y": 0},
                "params": {"duration_seconds": 0.1},
            }
        )
        edges.append(
            {
                "id": "e_00000001",
                "source": "n_00000003",
                "sourcePort": "flow",
                "target": "n_00000002",
                "targetPort": "flow",
                "order": 0,
            }
        )
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_ee10000001",
            "name": "triggers",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": nodes,
            "edges": edges,
        }
    )


def save(root: Path, document: WorkflowDocument) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "workflow.json").write_text(document.model_dump_json(), encoding="utf-8")


@pytest.mark.integration
def test_schedule_interval_health_and_stop(tmp_path: Path) -> None:
    """US-TRG-04/AC-1..4; US-TRG-07/AC-2: real interval jobs start and stop with lifecycle."""

    async def scenario() -> None:
        root = tmp_path / "schedule.weft"
        save(
            root,
            document({"schedule": {"enabled": True, "schedules": [{"interval_seconds": 0.05}]}}),
        )
        engine = Engine()
        registry = builtin_registry()
        engine.registry = registry
        coordinator = RunCoordinator(engine)
        manager = TriggerManager(coordinator, {})
        manager.activate(WorkflowStore(root).load(), root)
        assert manager.health["wf_ee10000001"]["schedule"]["next"]
        for _ in range(100):
            if engine.runs:
                break
            await asyncio.sleep(0.02)
        record = next(iter(engine.runs.values())).record
        assert record.trigger["source"] == "schedule"
        assert record.trigger["payload"]["schedule_id"]
        manager.deactivate("wf_ee10000001")
        count = len(engine.runs)
        await asyncio.sleep(0.08)
        assert len(engine.runs) == count
        manager.close()

    asyncio.run(scenario())
    with pytest.raises(ValueError):
        validate_trigger_config(document({"schedule": {"schedules": [{"cron": "bad"}]}}))


@pytest.mark.integration
def test_watch_debounce_ignore_and_health(tmp_path: Path) -> None:
    """US-TRG-05/AC-1..5: real watchdog debounces, ignores temp files and reports health."""

    async def scenario() -> None:
        root = tmp_path / "watch.weft"
        save(
            root,
            document(
                {"watch": {"enabled": True, "watches": [{"path": "data", "debounce_ms": 50}]}}
            ),
        )
        (root / "data").mkdir()
        engine = Engine()
        engine.registry = builtin_registry()
        coordinator = RunCoordinator(engine)
        manager = TriggerManager(coordinator, {})
        manager.activate(WorkflowStore(root).load(), root)
        target = root / "data" / "input.txt"
        target.write_text("one", encoding="utf-8")
        target.write_text("two", encoding="utf-8")
        (root / "data" / "ignored.tmp").write_text("x", encoding="utf-8")
        for _ in range(100):
            if engine.runs:
                break
            await asyncio.sleep(0.02)
        record = next(iter(engine.runs.values())).record
        assert record.trigger["source"] == "file"
        assert record.trigger["payload"]["events"][0]["path"] == str(target)
        assert "ignored.tmp" not in str(record.trigger["payload"])
        assert manager.health["wf_ee10000001"]["watch"]["status"] == "ok"
        manager.deactivate("wf_ee10000001")
        manager.close()

    asyncio.run(scenario())

    async def missing() -> None:
        root = tmp_path / "missing.weft"
        save(root, document({"watch": {"enabled": True, "watches": [{"path": "not-there"}]}}))
        engine = Engine()
        engine.registry = builtin_registry()
        manager = TriggerManager(RunCoordinator(engine), {})
        manager.activate(WorkflowStore(root).load(), root)
        assert manager.health["wf_ee10000001"]["watch"]["status"] == "error"
        manager.close()

    asyncio.run(missing())


def api_client(root: Path, doc: WorkflowDocument, config: Path) -> TestClient:
    save(root, doc)
    app = create_app(session=Session("test", "127.0.0.1", 7788, config / "session.json"))
    app.state.roots[doc.id] = root
    return TestClient(app, base_url="http://127.0.0.1:7788")


@pytest.mark.integration
def test_http_token_wait_response_rate_limit_and_disabled(tmp_path: Path) -> None:
    """US-TRG-06/AC-1..4; US-SBX-09/AC-1,2: HTTP trigger auth, wait and one response."""
    token = "trigger-secret"
    doc = document(
        {"http": {"enabled": True, "token_hash": HttpSource.token_hash(token)}},
        response=True,
    )
    with api_client(tmp_path / "http.weft", doc, tmp_path) as client:
        response = client.post(
            f"/api/workflows/{doc.id}/trigger?wait=true",
            json={"value": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 202
        assert response.json()["outputs"]["status_code"] == 201
        assert response.json()["outputs"]["body"] == {"ok": True}
        assert response.json()["status"] == "succeeded"
        assert client.post(f"/api/workflows/{doc.id}/trigger", json={}).status_code == 401
        for _ in range(10):
            client.post(f"/api/workflows/{doc.id}/trigger", json={})
        assert client.post(f"/api/workflows/{doc.id}/trigger", json={}).status_code == 429
    disabled = document({"http": {"enabled": False}})
    with api_client(tmp_path / "disabled.weft", disabled, tmp_path) as client:
        assert client.post(f"/api/workflows/{disabled.id}/trigger", json={}).status_code == 404


@pytest.mark.integration
def test_http_drop_wait_timeout_and_duplicate_response(tmp_path: Path, monkeypatch: Any) -> None:
    """US-TRG-06/AC-1,2,4; US-EXE-13/AC-5: drop wins, timeout keeps Run alive."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path))
    SettingsStore().update({"trigger": {"http_wait_timeout_s": 0.02}})
    doc = document(
        {"http": {"enabled": True, "token_hash": HttpSource.token_hash("token")}},
        response=True,
        wait=True,
    )
    doc.settings.concurrency_policy = "drop"
    root = tmp_path / "wait.weft"
    save(root, doc)

    async def scenario() -> None:
        engine = Engine()
        engine.registry = builtin_registry()
        coordinator = RunCoordinator(engine)
        source = HttpSource(coordinator)
        first = await source.trigger(doc, root, engine.registry, {}, "token", "local", True)
        assert first["wait_timed_out"] is True
        assert first["status"] in {"queued", "running"}
        dropped = await source.trigger(doc, root, engine.registry, {}, "token", "local", True)
        assert dropped == {"run_id": None, "disposition": "dropped"}
        await coordinator.wait(first["run_id"])
        assert engine.http_responses[first["run_id"]]["status_code"] == 201

    asyncio.run(scenario())

    from weft.workflow.models import Node

    duplicate = document({}, response=True)
    duplicate.nodes.append(
        Node.model_validate(
            {
                "id": "n_00000004",
                "type": "flow.http_response",
                "node_version": 1,
                "name": "Second response",
                "position": {"x": 0, "y": 0},
                "params": {},
            }
        )
    )

    async def two() -> None:
        engine = Engine()
        record = await engine.run(
            engine.prepare(duplicate, tmp_path / "duplicate", builtin_registry())
        )
        assert record.status == "failed"

    asyncio.run(two())


def test_nonlocal_listener_requires_global_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-SBX-09/AC-1,3: non-local listen needs a global token and reports a warning."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="global_token"):
        create_app(host="0.0.0.0", session=Session("", "0.0.0.0", 7788, tmp_path / "s.json"))
    SettingsStore(tmp_path / "config.toml").update({"server": {"global_token": "global"}})
    app = create_app(
        host="0.0.0.0", session=Session("global", "0.0.0.0", 7788, tmp_path / "s.json")
    )
    assert app.state.session.token == "global"


def test_unattended_excel_target_must_be_unique() -> None:
    """US-XLS-01/AC-4: ambiguous saved Excel targets fail before creating a Run."""
    from weft.workflow.models import Node

    doc = document({})
    doc.nodes.append(
        Node.model_validate(
            {
                "id": "n_00000005",
                "type": "excel.connect",
                "node_version": 1,
                "name": "Connect",
                "position": {"x": 0, "y": 0},
                "params": {"mode": "attach_visible", "target": {"workbook": "ref.xlsx"}},
            }
        )
    )

    class Worker:
        async def submit(self, method: str) -> list[dict[str, Any]]:
            return [{"workbooks": ["ref.xlsx"]}, {"workbooks": ["ref.xlsx"]}]

    with pytest.raises(ValueError, match="matches=2"):
        asyncio.run(precheck_excel_targets(doc, SimpleEngine(Worker())))


@pytest.mark.integration
def test_trigger_event_persistence_and_independent_source_activation(tmp_path: Path) -> None:
    """US-TRG-01/AC-2,3; US-TRG-07/AC-1: five sources derive from params and save events."""

    async def scenario() -> None:
        root = tmp_path / "event.weft"
        doc = document({"manual": {"enabled": True}})
        save(root, doc)
        engine = Engine()
        engine.registry = builtin_registry()
        manager = TriggerManager(RunCoordinator(engine), {})
        manager.activate(doc, root)
        assert set(manager.health[doc.id]) == {"manual", "chat", "schedule", "watch", "http"}
        assert manager.health[doc.id]["manual"]["enabled"] is True
        updated = document(
            {"manual": {"enabled": False}, "chat": {"enabled": True}, "http": {"enabled": True}}
        )
        manager.activate(updated, root)
        assert manager.health[doc.id]["manual"]["enabled"] is False
        assert manager.health[doc.id]["chat"]["enabled"] is True
        assert manager.health[doc.id]["http"]["enabled"] is True
        record = await engine.run(
            engine.prepare(
                updated,
                root,
                engine.registry,
                trigger={
                    "source": "chat",
                    "ts": "2026-01-01T00:00:00+00:00",
                    "session_id": "s_1",
                    "payload": {"message": "hello", "history_len": 0},
                },
            )
        )
        meta = json.loads(
            (root / ".runs" / record.run_id / "meta.json").read_text(encoding="utf-8")
        )
        assert meta["trigger"]["payload"]["message"] == "hello"
        assert meta["trigger"]["session_id"] == "s_1"
        manager.close()

    asyncio.run(scenario())


class SimpleEngine:
    def __init__(self, worker: Any) -> None:
        self.excel_worker = worker
