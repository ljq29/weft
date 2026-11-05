from __future__ import annotations

import tomllib
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from weft.api.app import create_app
from weft.nodes.registry import builtin_registry
from weft.worker.environment import EnvironmentError as WorkflowEnvironmentError
from weft.worker.environment import WorkflowEnvironment
from weft.workflow.demos import create_demo, list_demos
from weft.workflow.packaging import pack_workflow, preflight
from weft.workflow.store import WorkflowStore
from weft.workflow.validation import validate_workflow

TOKEN = "test-session-token"
HOST = "127.0.0.1:7788"


def test_builtin_demos_create_independent_valid_workflows_and_zip_packages(
    tmp_path: Path,
) -> None:
    """US-DES-01/AC-4: bundled demos are valid, portable and safe to instantiate."""
    registry = builtin_registry()
    demos = list_demos()
    assert {demo.id for demo in demos} == {"csv-sales", "table-transform", "llm-text"}
    for index, demo in enumerate(demos):
        root = create_demo(demo.id, f"demo-{index}", tmp_path)
        document = WorkflowStore(root).load()
        assert document.id.startswith("wf_")
        assert document.name == f"demo-{index}"
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        assert project["tool"]["weft"]["demo_id"] == demo.id
        assert not validate_workflow(document, registry.declarations_for(document)).errors
        report = preflight(root, registry)
        assert report.errors == ()
        archive_path = pack_workflow(root, tmp_path / f"{demo.id}.weft.zip", registry=registry)
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            assert f"{root.name}/workflow.json" in names
            assert f"{root.name}/uv.lock" in names
            assert f"{root.name}/vendor/weft_worker-0.4.0-py3-none-any.whl" in names
            lock = archive.read(f"{root.name}/uv.lock").decode("utf-8")
            assert 'source = { path = "vendor/weft_worker-0.4.0-py3-none-any.whl" }' in lock
            assert tmp_path.as_posix() not in lock
            assert not any("/.runs/" in name or "/.venv/" in name for name in names)
        if demo.id == "csv-sales":
            assert (root / "data" / "sales.csv").is_file()
        if demo.id == "llm-text":
            llm_node = next(node for node in document.nodes if node.type == "agent.llm_call")
            assert llm_node.params["llm"] == "demo"
            assert "<YOUR_API_KEY>" in (root / "workflow.json").read_text(encoding="utf-8")


def test_demo_catalog_api_creates_and_safely_replaces_only_same_demo(tmp_path: Path) -> None:
    """US-DES-01/AC-4: demo API replaces matching copies and rejects other directories."""
    app = create_app(token=TOKEN)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url=f"http://{HOST}") as api:
        response = api.get("/api/demos", headers=headers)
        assert response.status_code == 200
        assert len(response.json()) == 3
        created = api.post(
            "/api/demos/table-transform/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert created.status_code == 201
        result = created.json()
        root = tmp_path / "my-demo.weft"
        assert Path(result["path"]) == root
        loaded = api.get(f"/api/workflows/{result['id']}", headers=headers)
        assert loaded.status_code == 200
        assert loaded.json()["name"] == "my-demo"

        pyproject = root / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8").split("\n[tool.weft]")[0] + "\n",
            encoding="utf-8",
        )
        (root / "user-change.txt").write_text("old copy", encoding="utf-8")
        replaced = api.post(
            "/api/demos/table-transform/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert replaced.status_code == 201
        replacement = replaced.json()
        assert replacement["id"] != result["id"]
        assert Path(replacement["path"]) == root
        assert result["id"] not in app.state.roots
        assert result["id"] not in app.state.triggers.health
        assert replacement["id"] in app.state.triggers.health
        assert not (root / "user-change.txt").exists()
        project = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        assert project["tool"]["weft"]["demo_id"] == "table-transform"

        different_demo = api.post(
            "/api/demos/csv-sales/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert different_demo.status_code == 409
        ordinary = api.post(
            "/api/workflows",
            json={"name": "ordinary", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert ordinary.status_code == 201
        unmarked = api.post(
            "/api/demos/table-transform/create",
            json={"name": "ordinary", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert unmarked.status_code == 409
        missing = api.post(
            "/api/demos/not-a-demo/create",
            json={"name": "other", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert missing.status_code == 404


def test_demo_environment_failure_preserves_existing_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-DES-01/AC-4: staging synchronization failures leave the old copy untouched."""
    app = create_app(token=TOKEN)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url=f"http://{HOST}") as api:
        created = api.post(
            "/api/demos/table-transform/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert created.status_code == 201
        workflow_id = created.json()["id"]
        root = tmp_path / "my-demo.weft"
        marker = root / "user-change.txt"
        marker.write_text("keep me", encoding="utf-8")

        def fail_sync(self: WorkflowEnvironment) -> None:
            raise WorkflowEnvironmentError("sync failed")

        monkeypatch.setattr(WorkflowEnvironment, "sync", fail_sync)
        failed = api.post(
            "/api/demos/table-transform/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert failed.status_code == 400
        assert failed.json()["error"]["code"] == "DEMO_ENVIRONMENT_FAILED"
        assert marker.read_text(encoding="utf-8") == "keep me"
        assert WorkflowStore(root).load().id == workflow_id
        assert app.state.roots[workflow_id] == root
        assert not list(tmp_path.glob(".*.staging"))


def test_demo_replacement_failure_restores_copy_roots_and_triggers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-DES-01/AC-4: replacement failures restore the previous directory and registration."""
    app = create_app(token=TOKEN)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url=f"http://{HOST}") as api:
        created = api.post(
            "/api/demos/table-transform/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert created.status_code == 201
        workflow_id = created.json()["id"]
        root = tmp_path / "my-demo.weft"
        marker = root / "user-change.txt"
        marker.write_text("keep me", encoding="utf-8")
        original_rename = Path.rename

        def fail_staging_rename(source: Path, destination: Path) -> Path:
            if source.name.endswith(".staging"):
                raise OSError("simulated rename failure")
            return original_rename(source, destination)

        monkeypatch.setattr(Path, "rename", fail_staging_rename)
        failed = api.post(
            "/api/demos/table-transform/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert failed.status_code == 500
        assert failed.json()["error"]["code"] == "DEMO_REPLACE_FAILED"
        assert marker.read_text(encoding="utf-8") == "keep me"
        assert WorkflowStore(root).load().id == workflow_id
        assert app.state.roots[workflow_id] == root
        assert workflow_id in app.state.triggers.health
        assert not list(tmp_path.glob(".*.staging"))
        assert not list(tmp_path.glob(".*.backup"))


def test_demo_replacement_rejects_active_run_without_touching_copy(tmp_path: Path) -> None:
    """US-DES-01/AC-4: an active run prevents replacement of its workflow root."""
    app = create_app(token=TOKEN)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url=f"http://{HOST}") as api:
        created = api.post(
            "/api/demos/table-transform/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert created.status_code == 201
        workflow_id = created.json()["id"]
        root = tmp_path / "my-demo.weft"
        marker = root / "user-change.txt"
        marker.write_text("keep me", encoding="utf-8")
        app.state.engine.runs["run_active"] = SimpleNamespace(
            root=root, record=SimpleNamespace(status="running")
        )

        conflict = api.post(
            "/api/demos/table-transform/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "WORKFLOW_RUN_ACTIVE"
        assert marker.read_text(encoding="utf-8") == "keep me"
        assert WorkflowStore(root).load().id == workflow_id
        assert app.state.roots[workflow_id] == root
        assert not list(tmp_path.glob(".*.staging"))
