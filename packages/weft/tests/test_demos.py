from __future__ import annotations

import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from weft.api.app import create_app
from weft.nodes.registry import builtin_registry
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
        assert not validate_workflow(document, registry.declarations_for(document)).errors
        report = preflight(root, registry)
        assert report.errors == ()
        archive_path = pack_workflow(root, tmp_path / f"{demo.id}.weft.zip", registry=registry)
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            assert f"{root.name}/workflow.json" in names
            assert f"{root.name}/uv.lock" in names
            assert f"{root.name}/vendor/weft_worker-0.3.0-py3-none-any.whl" in names
            lock = archive.read(f"{root.name}/uv.lock").decode("utf-8")
            assert 'source = { path = "vendor/weft_worker-0.3.0-py3-none-any.whl" }' in lock
            assert tmp_path.as_posix() not in lock
            assert not any("/.runs/" in name or "/.venv/" in name for name in names)
        if demo.id == "csv-sales":
            assert (root / "data" / "sales.csv").is_file()
        if demo.id == "llm-text":
            llm_node = next(node for node in document.nodes if node.type == "agent.llm_call")
            assert llm_node.params["llm"] == "demo"
            assert "<YOUR_API_KEY>" in (root / "workflow.json").read_text(encoding="utf-8")


def test_demo_catalog_api_creates_workflow_and_rejects_conflicts(tmp_path: Path) -> None:
    """US-DES-01/AC-4: demo API lists templates and creates a selected copy."""
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
        assert Path(result["path"]) == tmp_path / "my-demo.weft"
        loaded = api.get(f"/api/workflows/{result['id']}", headers=headers)
        assert loaded.status_code == 200
        assert loaded.json()["name"] == "my-demo"
        conflict = api.post(
            "/api/demos/table-transform/create",
            json={"name": "my-demo", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert conflict.status_code == 409
        missing = api.post(
            "/api/demos/not-a-demo/create",
            json={"name": "other", "parent_dir": str(tmp_path)},
            headers=headers,
        )
        assert missing.status_code == 404
