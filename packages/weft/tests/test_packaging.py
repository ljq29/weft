from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from weft.agent.settings import SettingsStore
from weft.api.app import create_app
from weft.api.security import Session
from weft.cli import main
from weft.nodes.registry import builtin_registry
from weft.workflow.models import WorkflowDocument
from weft.workflow.packaging import (
    PackError,
    UnpackError,
    pack_workflow,
    preflight,
    unpack_workflow,
)
from weft.workflow.store import WorkflowStore

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def make_workflow(root: Path, params: dict[str, Any] | None = None) -> WorkflowDocument:
    root.mkdir(parents=True)
    (root / "nodes").mkdir()
    (root / "prompts").mkdir()
    (root / "data").mkdir()
    document = WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "portable",
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
                },
                {
                    "id": "n_00000002",
                    "type": "table.read_csv",
                    "node_version": 1,
                    "name": "Read",
                    "position": {"x": 100, "y": 0},
                    "params": params or {"path": "data/input.csv"},
                },
            ],
        }
    )
    (root / "workflow.json").write_text(document.model_dump_json(), encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\ndependencies = []\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "data" / "input.csv").write_text("value\n1\n", encoding="utf-8")
    return document


def test_pack_warnings_exclusions_and_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-PKG-01/AC-1,2; US-PKG-03/AC-1..4; US-PKG-04/AC-5; US-SBX-08/AC-3."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    root = tmp_path / "portable.weft"
    document = make_workflow(root, {"path": str(tmp_path / "external.csv")})
    (root / ".runs").mkdir()
    (root / ".runs" / "secret.txt").write_text("not packed", encoding="utf-8")
    (root / ".venv").mkdir()
    (root / ".venv" / "installed.txt").write_text("not packed", encoding="utf-8")
    report = preflight(root, builtin_registry())
    assert report.abs_paths[0]["param"] == "path"
    with pytest.raises(PackError):
        pack_workflow(root)
    archive = pack_workflow(root, confirm_warnings=True)
    with zipfile.ZipFile(archive) as zipped:
        assert all(name.startswith("portable.weft/") for name in zipped.namelist())
        assert "portable.weft/workflow.json" in zipped.namelist()
        assert "portable.weft/data/input.csv" in zipped.namelist()
        assert not any("/.runs/" in name or "/.venv/" in name for name in zipped.namelist())
    imported = unpack_workflow(archive, tmp_path / "imported", sync=False)
    assert WorkflowStore(imported).load().id == document.id
    excluded = pack_workflow(root, tmp_path / "no-data.zip", True, True)
    with zipfile.ZipFile(excluded) as zipped:
        assert "portable.weft/data/input.csv" not in zipped.namelist()


def test_pack_errors_and_real_secret_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """US-PKG-03/AC-4; US-SBX-08/AC-1..3: errors block and configured keys never ship."""
    config = tmp_path / "config"
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(config))
    secret = "unit-test-secret-value-1234567890"
    SettingsStore(config / "config.toml").update(
        {"llm": {"main": {"base_url": "http://localhost", "model": "test", "api_key": secret}}}
    )
    root = tmp_path / "portable.weft"
    make_workflow(root)
    (root / "data" / "input.csv").write_text(secret, encoding="utf-8")
    report = preflight(root, builtin_registry())
    assert any(item["code"] == "SECRET_DETECTED" for item in report.errors)
    assert secret not in json.dumps(report.as_dict())
    with pytest.raises(PackError):
        pack_workflow(root, confirm_warnings=True)
    (root / "data" / "input.csv").write_text("value\n1\n", encoding="utf-8")
    (root / "nodes" / "custom.py").write_text(
        "api_key = 'test-api-key-abcdefgh1234567890'\n", encoding="utf-8"
    )
    assert any(
        item["code"] == "POSSIBLE_HARDCODED_SECRET"
        for item in preflight(root, builtin_registry()).warnings
    )


def test_unpack_rejects_zip_slip_and_invalid_roots(tmp_path: Path) -> None:
    """US-PKG-04/AC-3: traversal, absolute and multi-root archives cannot escape."""
    for index, name in enumerate(("demo.weft/../escape", "C:/escape", "one/a")):
        archive = tmp_path / f"bad-{index}.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr(name, "bad")
            if index == 2:
                zipped.writestr("two/b", "bad")
        with pytest.raises(UnpackError):
            unpack_workflow(archive, tmp_path / f"target-{index}", sync=False)
        assert not (tmp_path / "escape").exists()


def test_pack_unpack_api_and_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """US-PKG-03/AC-1,2; US-PKG-04/AC-1,2: UI endpoints and CLI share packaging."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    root = tmp_path / "portable.weft"
    document = make_workflow(root)
    app = create_app(
        enable_triggers=False,
        session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"),
    )
    app.state.roots[document.id] = root
    monkeypatch.setattr("weft.workflow.packaging.WorkflowEnvironment.sync", lambda self: None)
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        auth = {"Authorization": "Bearer test"}
        report = client.get(f"/api/workflows/{document.id}/pack/preflight", headers=auth)
        assert report.status_code == 200
        packed = client.post(
            f"/api/workflows/{document.id}/pack",
            headers=auth,
            json={"exclude_data": False, "output": str(tmp_path / "api.zip")},
        )
        assert packed.status_code == 200, packed.text
        unpacked = client.post(
            "/api/workflows/unpack",
            headers=auth,
            json={"zip_path": str(tmp_path / "api.zip"), "dest_dir": str(tmp_path / "api-target")},
        )
        assert unpacked.status_code == 200, unpacked.text
        assert unpacked.json()["id"] == document.id
        from weft.worker.environment import EnvironmentError as WorkflowEnvironmentError

        def fail_sync(self: Any) -> None:
            raise WorkflowEnvironmentError("sync failed")

        monkeypatch.setattr("weft.workflow.packaging.WorkflowEnvironment.sync", fail_sync)
        failed = client.post(
            "/api/workflows/unpack",
            headers=auth,
            json={"zip_path": str(tmp_path / "api.zip"), "dest_dir": str(tmp_path / "failed")},
        )
        assert failed.status_code == 400
        assert failed.json()["error"]["code"] == "UNPACK_FAILED"
        assert not (tmp_path / "failed" / "portable.weft").exists()
        monkeypatch.setattr("weft.workflow.packaging.WorkflowEnvironment.sync", lambda self: None)
    output = tmp_path / "cli.zip"
    assert main(["pack", str(root), "-o", str(output), "--json"]) == 0
    assert main(["unpack", str(output), "-d", str(tmp_path / "cli-target"), "--json"]) == 0


@pytest.mark.integration
def test_pack_unpack_run_in_independent_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-PKG-01/AC-2; US-PKG-04/AC-4,5: local-wheel handoff executes after source removal."""
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    root = tmp_path / "portable.weft"
    make_workflow(root)
    (root / "uv.lock").unlink()
    wheels = root / "wheels"
    environment = {**os.environ, "UV_INDEX_URL": "https://pypi.tuna.tsinghua.edu.cn/simple"}
    for package in ("weft-sdk", "weft-worker"):
        subprocess.run(
            [
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                str(wheels),
                str(PROJECT_ROOT / "packages" / package),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=environment,
        )
    (root / "pyproject.toml").write_text(
        """[project]
name = "portable"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["weft-worker==0.1.0", "weft-sdk==0.1.0"]
[tool.uv.sources]
weft-worker = { path = "wheels/weft_worker-0.1.0-py3-none-any.whl" }
weft-sdk = { path = "wheels/weft_sdk-0.1.0-py3-none-any.whl" }
""",
        encoding="utf-8",
    )
    locked = subprocess.run(
        ["uv", "lock"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=environment,
    )
    assert locked.returncode == 0, locked.stdout + locked.stderr
    nodes = json.loads((root / "workflow.json").read_text(encoding="utf-8"))["nodes"]
    nodes.append(
        {
            "id": "n_00000003",
            "type": "table.write_csv",
            "node_version": 1,
            "name": "Write",
            "position": {"x": 200, "y": 0},
            "params": {"path": "out/result.csv"},
        }
    )
    document = json.loads((root / "workflow.json").read_text(encoding="utf-8"))
    document["nodes"] = nodes
    document["edges"] = [
        {
            "id": "e_00000001",
            "source": "n_00000002",
            "sourcePort": "out",
            "target": "n_00000003",
            "targetPort": "in",
            "order": 0,
        }
    ]
    (root / "workflow.json").write_text(json.dumps(document), encoding="utf-8")
    checked = preflight(root, builtin_registry())
    assert not checked.errors and not checked.warnings, checked.as_dict()
    archive = pack_workflow(root, tmp_path / "handoff.zip")
    imported = unpack_workflow(archive, tmp_path / "machine-b")
    assert WorkflowStore(imported).load().id == "wf_0123456789ab"
    original = root.with_name("machine-a-original")
    root.rename(original)
    result = subprocess.run(
        [sys.executable, "-m", "weft", "run", str(imported), "--wait"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**environment, "WEFT_CONFIG_DIR": str(tmp_path / "run-config")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (imported / "out" / "result.csv").read_text(encoding="utf-8-sig").splitlines() == [
        "value",
        "1",
    ]
