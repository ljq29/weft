from __future__ import annotations

import difflib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from weft.sandbox.base import NoneSandbox
from weft.sandbox.changes import Change, ChangeSet, file_hash


class ProtectedChangeError(ValueError):
    pass


def detect_renames(changeset: ChangeSet) -> ChangeSet:
    deleted = [change for change in changeset.changes if change.kind == "deleted"]
    created = [change for change in changeset.changes if change.kind == "created"]
    used_deleted: set[str] = set()
    used_created: set[str] = set()
    renamed: list[Change] = []
    for new in created:
        if new.source is None:
            continue
        current_hash = file_hash(new.source)
        matches = [
            old
            for old in deleted
            if old.path not in used_deleted and old.baseline_hash == current_hash
        ]
        if len(matches) != 1:
            continue
        old = matches[0]
        used_deleted.add(old.path)
        used_created.add(new.path)
        renamed.append(
            Change(
                path=new.path,
                rel_root=new.rel_root,
                kind="renamed",
                old_path=old.path,
                new_path=new.path,
                baseline_hash=old.baseline_hash,
                size=new.size,
                is_text=new.is_text,
                protected=new.protected or old.protected,
                source=new.source,
            )
        )
    if len(created) != len(used_created) and deleted:
        changeset.audit_warnings.append(
            "Ambiguous content hashes were left as delete/create instead of rename"
        )
    changeset.changes = [
        change
        for change in changeset.changes
        if not (
            (change.kind == "deleted" and change.path in used_deleted)
            or (change.kind == "created" and change.path in used_created)
        )
    ] + renamed
    return changeset


class ChangeReviewStore:
    def __init__(self, root: Path, run_id: str) -> None:
        self.root = root.resolve()
        self.run_id = run_id
        self.path = root / ".runs" / run_id / "changes.json"

    def load(self) -> ChangeSet:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        sandbox_root: Path | None = None
        none_sandbox: NoneSandbox | None = None
        if data["sandbox"] == "sandboxie":
            record = json.loads(
                (self.root / ".runs" / self.run_id / "sandbox.json").read_text(encoding="utf-8")
            )
            if record.get("run_id") != self.run_id:
                raise ValueError("Sandbox ownership does not match this Run")
            sandbox_root = Path(record["sandbox_root"])
        else:
            none_sandbox = NoneSandbox(
                self.root,
                self.run_id,
                [Path(path) for path in data.get("authorized_roots", [])],
            )
        changes = []
        for item in data["changes"]:
            path = Path(item["path"])
            logical = Path(item.get("new_path") or item["path"])
            if sandbox_root is not None:
                resolved = logical.resolve()
                home = Path.home().resolve()
                if resolved.is_relative_to(home):
                    source = sandbox_root / "user" / "current" / resolved.relative_to(home)
                else:
                    drive = resolved.drive.rstrip(":\\")
                    source = (
                        sandbox_root / "drive" / drive / resolved.relative_to(Path(resolved.anchor))
                    )
            else:
                assert none_sandbox is not None
                source = (
                    none_sandbox._tombstone(path)
                    if item["kind"] == "deleted"
                    else none_sandbox._shadow_path(logical)
                )
            changes.append(Change(**item, source=source))
        return ChangeSet(
            run_id=data["run_id"],
            sandbox=data["sandbox"],
            changes=changes,
            audit_complete=data["audit_complete"],
            audit_warnings=data.get("audit_warnings", []),
            collected_at=data["collected_at"],
            authorized_roots=data.get("authorized_roots", []),
        )

    def save(self, changeset: ChangeSet) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(changeset.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def diff(self, path: Path) -> dict[str, Any]:
        changeset = self.load()
        change = self._find(changeset, path)
        old_data = b""
        if change.baseline_hash:
            baseline = (
                self.root
                / ".runs"
                / self.run_id
                / "baseline"
                / f"{change.baseline_hash.removeprefix('sha256:')}.data"
            )
            if baseline.is_file():
                old_data = baseline.read_bytes()
        new_data = (
            change.source.read_bytes()
            if change.source is not None and change.source.is_file() and change.kind != "deleted"
            else b""
        )
        old_text = old_data.decode("utf-8") if change.is_text else ""
        new_text = new_data.decode("utf-8") if change.is_text else ""
        return {
            "path": change.path,
            "kind": change.kind,
            "old_path": change.old_path,
            "new_path": change.new_path,
            "is_text": change.is_text,
            "baseline_hash": change.baseline_hash,
            "size": change.size,
            "diff": "\n".join(
                difflib.unified_diff(
                    old_text.splitlines(),
                    new_text.splitlines(),
                    fromfile=change.old_path or change.path,
                    tofile=change.new_path or change.path,
                    lineterm="",
                )
            ),
            "audit_complete": changeset.audit_complete,
            "audit_warnings": changeset.audit_warnings,
        }

    def apply(self, paths: list[Path], overwrite_conflicts: bool = False) -> list[Change]:
        changeset = self.load()
        requested = [self._find(changeset, path) for path in paths]
        if any(change.protected for change in requested):
            raise ProtectedChangeError("Protected paths cannot be applied")
        results = []
        for change in requested:
            if change.state == "applied":
                results.append(change)
                continue
            if change.state == "discarded":
                results.append(change)
                continue
            target = Path(change.new_path or change.path)
            baseline = change.baseline_hash
            expected = None if change.kind in {"created", "renamed"} else baseline
            stale = file_hash(target) != expected
            if change.kind == "renamed" and change.old_path:
                stale = stale or file_hash(Path(change.old_path)) != baseline
            if stale:
                if not overwrite_conflicts:
                    change.state = "conflict"
                    change.error = "CHANGE_CONFLICT"
                    results.append(change)
                    self.save(changeset)
                    continue
            try:
                if change.kind == "deleted":
                    self._backup(target)
                    target.unlink(missing_ok=True)
                else:
                    if target.exists():
                        self._backup(target)
                    if change.source is None or not change.source.is_file():
                        raise FileNotFoundError(change.source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name(f"{target.name}.weft-{uuid.uuid4().hex}.tmp")
                    shutil.copyfile(change.source, temporary)
                    os.replace(temporary, target)
                    if change.kind == "renamed" and change.old_path:
                        old = Path(change.old_path)
                        self._backup(old)
                        old.unlink(missing_ok=True)
                change.state = "applied"
                change.error = None
            except Exception as error:
                change.state = "failed"
                change.error = str(error)
            results.append(change)
            self.save(changeset)
        return results

    def discard(self, paths: list[Path] | None = None) -> list[Change]:
        changeset = self.load()
        selected = (
            changeset.changes if paths is None else [self._find(changeset, path) for path in paths]
        )
        for change in selected:
            if change.state != "applied":
                change.state = "discarded"
                change.error = None
                if change.source is not None:
                    change.source.unlink(missing_ok=True)
        self.save(changeset)
        return selected

    def auto_apply(self) -> list[Change]:
        changeset = self.load()
        paths = [
            Path(change.path)
            for change in changeset.changes
            if change.state == "pending" and change.rel_root is not None and not change.protected
        ]
        return self.apply(paths) if paths else []

    def _find(self, changeset: ChangeSet, path: Path) -> Change:
        for change in changeset.changes:
            if Path(change.path) == path or (
                change.old_path is not None and Path(change.old_path) == path
            ):
                return change
        raise ValueError(f"Change not found: {path}")

    def _backup(self, path: Path) -> None:
        if not path.is_file():
            return
        directory = self.root / ".runs" / self.run_id / "backups" / uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, directory / path.name)
