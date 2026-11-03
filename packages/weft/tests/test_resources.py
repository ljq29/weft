from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from weft.api.app import create_app
from weft.api.security import Session
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument, WorkflowStore
from weft.workflow.resources import preflight_resources


def node(node_id: str, node_type: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "node_version": 1,
        "name": node_type,
        "position": {"x": 0, "y": 0},
        "params": params,
    }


def document(nodes: list[dict[str, Any]]) -> WorkflowDocument:
    return WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "resources",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": nodes,
        }
    )


class FakeExcel:
    def __init__(self) -> None:
        self.opened: list[str] = []

    async def submit(self, method: str) -> list[dict[str, Any]]:
        assert method == "list_instances"
        return [{"workbooks": self.opened}]


@pytest.mark.integration
def test_resource_preflight_is_read_only_and_aggregates(tmp_path: Path, monkeypatch) -> None:
    """US-PKG-07/AC-1,2: all declared resources are checked read-only within two seconds."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    nodes = [
        node("n_00000001", "flow.trigger", {}),
        node("n_00000002", "table.read_csv", {"path": "data/input.csv"}),
        node("n_00000003", "agent.llm_call", {"llm": "ready", "user_prompt": "hi"}),
        node(
            "n_00000004",
            "agent.pi",
            {"task": "hi", "llm": "ready", "pi_path": str(tmp_path / "pi.exe")},
        ),
        node("n_00000005", "excel.workbook", {"mode": "open_existing", "name": "ready.xlsx"}),
    ]
    graph = document(nodes)
    registry = builtin_registry()
    engine = SimpleNamespace(excel_worker=FakeExcel())

    async def check() -> dict[str, Any]:
        return await preflight_resources(graph, tmp_path, registry, engine)

    import asyncio

    started = time.perf_counter()
    missing = asyncio.run(check())
    assert time.perf_counter() - started < 2
    assert not missing["ok"]
    assert {item["node_id"] for item in missing["missing"]} == {
        "n_00000002",
        "n_00000003",
        "n_00000004",
        "n_00000005",
    }
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "input.csv").write_text("value\n1\n", encoding="utf-8")
    (tmp_path / "pi.exe").write_bytes(b"fake")
    from weft.agent.settings import SettingsStore

    SettingsStore().update(
        {"llm": {"ready": {"base_url": "http://localhost", "model": "test", "api_key": ""}}}
    )
    engine.excel_worker.opened = ["ready.xlsx"]
    before = {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    ready = asyncio.run(check())
    assert ready["ok"], ready["missing"]
    after = {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


@pytest.mark.integration
def test_run_resource_preflight_requires_explicit_override(tmp_path: Path, monkeypatch) -> None:
    """US-PKG-07/AC-1: API aggregates missing resources and honors explicit confirmation."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    graph = document(
        [
            node("n_00000001", "flow.trigger", {}),
            node("n_00000002", "table.read_csv", {"path": "data/missing.csv"}),
        ]
    )
    root = tmp_path / "resources.weft"
    root.mkdir()
    WorkflowStore(root).path.write_text(graph.model_dump_json(), encoding="utf-8")
    app = create_app(
        enable_triggers=False,
        session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"),
    )
    app.state.roots[graph.id] = root
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        auth = {"Authorization": "Bearer test"}
        report = client.get(f"/api/workflows/{graph.id}/resources/preflight", headers=auth)
        assert report.status_code == 200
        assert report.json()["missing"][0]["param"] == "path"
        blocked = client.post(f"/api/workflows/{graph.id}/runs", headers=auth, json={})
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "MISSING_EXTERNAL_RESOURCES"
        assert not app.state.engine.runs
        allowed = client.post(
            f"/api/workflows/{graph.id}/runs",
            headers=auth,
            json={"allow_missing_resources": True},
        )
        assert allowed.status_code == 202
        assert allowed.json()["disposition"] == "started"
