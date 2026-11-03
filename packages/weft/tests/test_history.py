from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from weft.api.app import create_app
from weft.api.security import Session
from weft.workflow import WorkflowDocument
from weft.workflow.history import RunHistory


def make_workflow(root: Path) -> WorkflowDocument:
    root.mkdir(parents=True)
    document = WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "history",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": [
                {
                    "id": "n_00000001",
                    "type": "flow.trigger",
                    "node_version": 1,
                    "name": "Trigger",
                    "position": {"x": 0, "y": 0},
                    "params": {"manual": {"enabled": True}},
                }
            ],
        }
    )
    (root / "workflow.json").write_text(document.model_dump_json(), encoding="utf-8")
    return document


@pytest.mark.integration
def test_history_disk_snapshots_and_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-EXE-09/AC-1..4: disk history remains readable and retains the newest Runs."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    root = tmp_path / "history.weft"
    document = make_workflow(root)
    app = create_app(
        enable_triggers=False,
        session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"),
    )
    app.state.roots[document.id] = root
    auth = {"Authorization": "Bearer test"}
    run_ids = []
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        for _ in range(2):
            submitted = client.post(f"/api/workflows/{document.id}/runs", headers=auth, json={})
            run_id = submitted.json()["run_id"]
            run_ids.append(run_id)
            for _ in range(100):
                time.sleep(0.01)
                record = client.get(f"/api/runs/{run_id}", headers=auth).json()
                if record["status"] == "succeeded":
                    break
            assert record["status"] == "succeeded"
        history = client.get(f"/api/workflows/{document.id}/runs?limit=20", headers=auth).json()
        assert [item["run_id"] for item in history] == list(reversed(run_ids))
        assert history[0]["trigger_source"] == "manual"
        assert {"started_at", "finished_at", "status"} <= history[0].keys()
        assert client.get(f"/api/runs/{run_ids[0]}/log", headers=auth).json()
        app.state.engine.runs.clear()
        disk = client.get(f"/api/runs/{run_ids[0]}", headers=auth)
        assert disk.status_code == 200
        assert disk.json()["nodes"]["n_00000001"]["status"] == "executed"
        assert client.get(f"/api/runs/{run_ids[0]}/log", headers=auth).json()
        table = client.get(f"/api/runs/{run_ids[0]}/nodes/n_00000001/ports/table", headers=auth)
        assert table.status_code == 200
        import pyarrow as pa

        assert pa.ipc.open_stream(table.content).read_all().num_rows == 0
        trace_path = root / ".runs" / run_ids[0] / "nodes" / "n_00000001.trace.jsonl"
        trace_path.parent.mkdir(exist_ok=True)
        trace_path.write_text('{"type":"llm","turn":1}\n', encoding="utf-8")
        trace = client.get(f"/api/runs/{run_ids[0]}/nodes/n_00000001/trace", headers=auth).json()
        assert trace == [{"type": "llm", "turn": 1}]
        assert not (trace_path.parent / "n_00000001.json").exists()
        updated = client.put("/api/settings", headers=auth, json={"cache": {"run_retention": 1}})
        assert updated.status_code == 200
        assert app.state.coordinator.run_retention == 1
        submitted = client.post(f"/api/workflows/{document.id}/runs", headers=auth, json={})
        third = submitted.json()["run_id"]
        for _ in range(100):
            time.sleep(0.01)
            if client.get(f"/api/runs/{third}", headers=auth).json()["status"] == "succeeded":
                break
        for _ in range(100):
            time.sleep(0.01)
            latest = client.get(f"/api/workflows/{document.id}/runs", headers=auth).json()
            if [item["run_id"] for item in latest] == [third]:
                break
        assert [item["run_id"] for item in latest] == [third]
        assert not (root / ".runs" / run_ids[0]).exists()
        assert (root / ".runs" / third / "meta.json").exists()


def test_history_retention_preserves_non_run_directories(tmp_path: Path) -> None:
    """US-EXE-09/AC-4: cleanup is bounded to valid Run directories."""
    root = tmp_path / "history.weft"
    make_workflow(root)
    for index in range(3):
        path = root / ".runs" / f"r_2026010{index + 1}_000000_000{index}"
        path.mkdir(parents=True)
        (path / "meta.json").write_text("{}", encoding="utf-8")
    (root / ".runs" / "cache").mkdir()
    (root / ".runs" / "chat").mkdir()
    deleted = RunHistory(root).cleanup(2)
    assert deleted == ["r_20260101_000000_0000"]
    assert (root / ".runs" / "cache").is_dir()
    assert (root / ".runs" / "chat").is_dir()
    with pytest.raises(ValueError):
        RunHistory(root).path("../escape")
