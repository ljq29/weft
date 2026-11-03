from __future__ import annotations

import json
from pathlib import Path

import pytest
from weft.agent.settings import SettingsStore
from weft.sandbox.base import NoneSandbox, SandboxCapabilityError, create_sandbox


def test_none_sandbox_setting_is_explicit(tmp_path: Path) -> None:
    """US-SBX-01/AC-1,3: none requires explicit opt-in and only enables shadow mode."""
    store = SettingsStore(tmp_path / "config.toml")
    with pytest.raises(SandboxCapabilityError, match="NoneSandbox is disabled"):
        create_sandbox(tmp_path, "r_none", "none", store)
    store.update({"sandbox": {"default": "none", "allow_none_sandbox": False}})
    with pytest.raises(SandboxCapabilityError):
        create_sandbox(tmp_path, "r_none", "inherit", store)
    store.update({"sandbox": {"default": "none", "allow_none_sandbox": True}})
    sandbox = create_sandbox(tmp_path, "r_none", "inherit", store)
    assert isinstance(sandbox, NoneSandbox)
    with pytest.raises(SandboxCapabilityError, match="spawn/bash/pi"):
        sandbox.spawn(["python", "-c", "print(1)"], tmp_path, {}, 1)


def test_shadow_write_edit_list_delete_and_collect(tmp_path: Path) -> None:
    """US-SBX-01/AC-2: all NoneSandbox writes stay in the per-Run shadow directory."""
    (tmp_path / "data").mkdir()
    actual = tmp_path / "data" / "note.txt"
    actual.write_text("before", encoding="utf-8")
    sandbox = NoneSandbox(tmp_path, "r_shadow")
    sandbox.write_file(actual, b"after")
    assert actual.read_text(encoding="utf-8") == "before"
    assert sandbox.read_file(actual) == b"after"
    sandbox.edit_file(actual, "after", "edited")
    assert sandbox.read_file(actual) == b"edited"
    with pytest.raises(ValueError, match="exactly once"):
        sandbox.edit_file(actual, "missing", "x")
    created = tmp_path / "data" / "new.txt"
    sandbox.write_file(created, "中文".encode())
    assert not created.exists()
    assert {entry.name for entry in sandbox.list_dir(tmp_path / "data", "*.txt")} == {
        "note.txt",
        "new.txt",
    }
    changes = sandbox.collect_changes()
    by_path = {change.path: change for change in changes.changes}
    assert by_path[str(actual)].kind == "modified"
    assert by_path[str(created)].kind == "created"
    assert by_path[str(created)].is_text is True
    sandbox.delete_file(actual)
    assert actual.read_text(encoding="utf-8") == "before"
    assert not sandbox.list_dir(tmp_path / "data", "note.txt")
    deleted = sandbox.collect_changes()
    assert (
        next(change for change in deleted.changes if change.path == str(actual)).kind == "deleted"
    )
    report = json.loads(
        (tmp_path / ".runs" / "r_shadow" / "changes.json").read_text(encoding="utf-8")
    )
    assert report["sandbox"] == "none" and report["audit_complete"] is True


def test_sandbox_rejects_unauthorized_and_marks_protected(tmp_path: Path) -> None:
    """US-SBX-05/AC-4: protected files are simulated but cannot be applied."""
    sandbox = NoneSandbox(tmp_path, "r_protected")
    with pytest.raises(SandboxCapabilityError, match="authorized roots"):
        sandbox.write_file(tmp_path.parent / "outside.txt", b"no")
    workflow = tmp_path / "workflow.json"
    workflow.write_text("{}", encoding="utf-8")
    sandbox.write_file(workflow, b'{"changed":true}')
    assert workflow.read_text(encoding="utf-8") == "{}"
    change = sandbox.collect_changes().changes[0]
    assert change.protected is True
    sandbox.discard()
    assert not sandbox.shadow.exists()
