from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from weft.api.security import config_dir

ChangeKind = Literal["created", "modified", "deleted", "renamed"]
ChangeState = Literal["pending", "applied", "conflict", "failed", "discarded"]


def file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def protected_path(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    root = root.resolve()
    if resolved == (config_dir() / "config.toml").resolve():
        return True
    if not resolved.is_relative_to(root):
        return False
    relative = resolved.relative_to(root)
    return relative.as_posix() in {"workflow.json", "pyproject.toml", "uv.lock"} or (
        bool(relative.parts) and relative.parts[0] == ".runs"
    )


def relative_to_root(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


@dataclass
class Change:
    path: str
    kind: ChangeKind
    size: int
    is_text: bool
    protected: bool
    baseline_hash: str | None
    rel_root: str | None = None
    old_path: str | None = None
    new_path: str | None = None
    state: ChangeState = "pending"
    error: str | None = None
    source: Path | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "rel_root": self.rel_root,
            "kind": self.kind,
            "old_path": self.old_path,
            "new_path": self.new_path,
            "baseline_hash": self.baseline_hash,
            "size": self.size,
            "is_text": self.is_text,
            "protected": self.protected,
            "state": self.state,
            "error": self.error,
        }


@dataclass
class ChangeSet:
    run_id: str
    sandbox: str
    changes: list[Change]
    audit_complete: bool = True
    audit_warnings: list[str] = field(default_factory=list)
    collected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    authorized_roots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "collected_at": self.collected_at,
            "sandbox": self.sandbox,
            "audit_complete": self.audit_complete,
            "audit_warnings": self.audit_warnings,
            "authorized_roots": self.authorized_roots,
            "changes": [change.to_dict() for change in self.changes],
        }


def baseline_files(roots: list[Path]) -> dict[Path, str]:
    baseline: dict[Path, str] = {}
    for root in roots:
        if root.is_file():
            baseline[root.resolve()] = file_hash(root) or ""
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if relative.parts[0] in {".runs", ".venv", "__pycache__"}:
                continue
            baseline[path.resolve()] = file_hash(path) or ""
    return baseline


def snapshot_baseline(baseline: dict[Path, str], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path, digest in baseline.items():
        target = directory / f"{digest.removeprefix('sha256:')}.data"
        if not target.exists():
            shutil.copyfile(path, target)
