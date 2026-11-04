from __future__ import annotations

from pathlib import Path

import pytest
from weft.sandbox.base import NoneSandbox
from weft.sandbox.review import ChangeReviewStore, ProtectedChangeError


def test_review_diff_stale_conflict_backup_and_idempotency(tmp_path: Path) -> None:
    """US-SBX-04/AC-1,3; US-SBX-05/AC-1,2,5: stale changes never overwrite silently."""
    target = tmp_path / "data" / "note.txt"
    target.parent.mkdir(parents=True)
    target.write_text("before\nkeep\n", encoding="utf-8")
    sandbox = NoneSandbox(tmp_path, "r_review")
    sandbox.write_file(target, b"after\nkeep\n")
    sandbox.collect_changes()
    store = ChangeReviewStore(tmp_path, "r_review")
    diff = store.diff(target)
    assert "-before" in diff["diff"] and "+after" in diff["diff"]
    assert diff["audit_complete"] is True
    target.write_text("external\n", encoding="utf-8")
    conflict = store.apply([target])[0]
    assert conflict.state == "conflict" and conflict.error == "CHANGE_CONFLICT"
    assert target.read_text(encoding="utf-8") == "external\n"
    applied = store.apply([target], overwrite_conflicts=True)[0]
    assert applied.state == "applied"
    assert target.read_text(encoding="utf-8") == "after\nkeep\n"
    assert list((tmp_path / ".runs" / "r_review" / "backups").rglob("note.txt"))
    assert store.apply([target])[0].state == "applied"
    assert store.load().changes[0].state == "applied"


def test_rename_detection_apply_and_discard(tmp_path: Path) -> None:
    """US-SBX-04/AC-2; US-SBX-05/AC-3,5: rename by hash and persistent discard."""
    old = tmp_path / "old.txt"
    old.write_text("same-content", encoding="utf-8")
    new = tmp_path / "new.txt"
    sandbox = NoneSandbox(tmp_path, "r_rename")
    sandbox.write_file(new, b"same-content")
    sandbox.delete_file(old)
    changeset = sandbox.collect_changes()
    assert len(changeset.changes) == 1
    change = changeset.changes[0]
    assert change.kind == "renamed"
    assert change.old_path == str(old) and change.new_path == str(new)
    store = ChangeReviewStore(tmp_path, "r_rename")
    assert store.apply([new])[0].state == "applied"
    assert not old.exists() and new.read_text(encoding="utf-8") == "same-content"

    other = tmp_path / "other.txt"
    sandbox.write_file(other, b"discard")
    sandbox.collect_changes()
    store.discard([other])
    assert store.load().changes[0].state == "discarded"
    assert not other.exists()


def test_ambiguous_hashes_do_not_become_rename(tmp_path: Path) -> None:
    """US-SBX-04/AC-2: ambiguous copies remain separate delete/create entries."""
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("same", encoding="utf-8")
    second.write_text("same", encoding="utf-8")
    sandbox = NoneSandbox(tmp_path, "r_ambiguous")
    created = tmp_path / "created.txt"
    sandbox.write_file(created, b"same")
    sandbox.delete_file(first)
    sandbox.delete_file(second)
    changeset = sandbox.collect_changes()
    assert {change.kind for change in changeset.changes} == {"created", "deleted"}
    assert changeset.audit_warnings


def test_protected_apply_is_rejected_and_auto_apply_stays_in_root(tmp_path: Path) -> None:
    """US-AGT-11/AC-3; US-SBX-05/AC-3,4: protected graph files and external paths stay blocked."""
    workflow = tmp_path / "workflow.json"
    workflow.write_text("{}", encoding="utf-8")
    external_root = tmp_path.parent / f"{tmp_path.name}-external"
    sandbox = NoneSandbox(tmp_path, "r_scope", [external_root])
    sandbox.write_file(workflow, b'{"changed":true}')
    sandbox.write_file(tmp_path / "inside.txt", b"inside")
    sandbox.write_file(external_root / "outside.txt", b"outside")
    sandbox.collect_changes()
    store = ChangeReviewStore(tmp_path, "r_scope")
    with pytest.raises(ProtectedChangeError):
        store.apply([workflow])
    assert workflow.read_text(encoding="utf-8") == "{}"
    store.auto_apply()
    assert (tmp_path / "inside.txt").read_text(encoding="utf-8") == "inside"
    assert not (external_root / "outside.txt").exists()
    assert workflow.read_text(encoding="utf-8") == "{}"


@pytest.mark.integration
def test_change_review_api_conflict_and_protected_response(tmp_path: Path) -> None:
    """US-SBX-04/AC-3; US-SBX-05/AC-1,2,4: review APIs preserve per-item semantics."""
    from fastapi.testclient import TestClient
    from weft.api.app import create_app
    from weft.api.security import Session
    from weft.nodes.registry import builtin_registry
    from weft.workflow import WorkflowDocument

    app = create_app(session=Session("test", "127.0.0.1", 7788, tmp_path / "session.json"))
    document = WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_dd10000001",
            "name": "review-api",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": [
                {
                    "id": "n_00000001",
                    "type": "flow.trigger",
                    "node_version": 1,
                    "name": "Trigger",
                    "position": {"x": 0, "y": 0},
                    "params": {},
                }
            ],
        }
    )
    app.state.engine.prepare(document, tmp_path, builtin_registry(), run_id="r_api")
    target = tmp_path / "note.txt"
    target.write_text("old", encoding="utf-8")
    sandbox = NoneSandbox(tmp_path, "r_api")
    sandbox.write_file(target, b"new")
    sandbox.write_file(tmp_path / "workflow.json", b"{}")
    sandbox.collect_changes()
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        client.headers["Authorization"] = "Bearer test"
        listing = client.get("/api/runs/r_api/changes")
        assert listing.status_code == 200
        assert len(listing.json()["changes"]) == 2
        target.write_text("external", encoding="utf-8")
        conflict = client.post("/api/runs/r_api/changes/apply", json={"paths": [str(target)]})
        assert conflict.status_code == 200
        assert conflict.json()["results"][0]["error"] == "CHANGE_CONFLICT"
        protected = client.post(
            "/api/runs/r_api/changes/apply",
            json={"paths": [str(tmp_path / "workflow.json")]},
        )
        assert protected.status_code == 400
        assert protected.json()["error"]["code"] == "PROTECTED_CHANGE"


def test_empty_or_incomplete_audit_remains_explicit(tmp_path: Path) -> None:
    """US-SBX-04/AC-4: empty complete audits stay quiet; incomplete audits remain visible."""
    from weft.sandbox.changes import ChangeSet

    empty = NoneSandbox(tmp_path, "r_empty").collect_changes()
    assert empty.audit_complete is True and empty.changes == []
    incomplete = ChangeSet(
        run_id="r_empty",
        sandbox="none",
        changes=[],
        audit_complete=False,
        audit_warnings=["unknown change"],
    )
    store = ChangeReviewStore(tmp_path, "r_empty")
    store.save(incomplete)
    loaded = store.load()
    assert loaded.audit_complete is False
    assert loaded.audit_warnings == ["unknown change"]
