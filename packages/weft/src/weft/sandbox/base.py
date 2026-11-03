from __future__ import annotations

import fnmatch
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from weft.agent.settings import SettingsStore
from weft.sandbox.changes import (
    Change,
    ChangeSet,
    baseline_files,
    file_hash,
    protected_path,
    relative_to_root,
    snapshot_baseline,
)


class SandboxCapabilityError(PermissionError):
    pass


@dataclass(frozen=True)
class SandboxEntry:
    path: str
    name: str
    is_dir: bool
    size: int


class SandboxProcess(Protocol):
    def wait(self, timeout: float | None = None) -> int: ...


class Sandbox(Protocol):
    def spawn(
        self, cmd: list[str], cwd: Path, env: dict[str, str], timeout: float
    ) -> SandboxProcess: ...
    def read_file(self, path: Path) -> bytes: ...
    def write_file(self, path: Path, data: bytes) -> None: ...
    def list_dir(self, path: Path, pattern: str | None = None) -> list[SandboxEntry]: ...
    def collect_changes(self) -> ChangeSet: ...
    def apply(self, changes: list[Change], overwrite_conflicts: bool = False) -> list[Change]: ...
    def discard(self) -> None: ...


class NoneSandbox:
    def __init__(self, root: Path, run_id: str, authorized_roots: list[Path] | None = None) -> None:
        self.root = root.resolve()
        self.run_id = run_id
        self.authorized_roots = [self.root, *(authorized_roots or [])]
        self.shadow = self.root / ".runs" / run_id / "shadow"
        self.baseline = baseline_files(self.authorized_roots)
        snapshot_baseline(self.baseline, self.root / ".runs" / run_id / "baseline")
        self._logical: dict[Path, Path] = {}

    def spawn(
        self, cmd: list[str], cwd: Path, env: dict[str, str], timeout: float
    ) -> SandboxProcess:
        raise SandboxCapabilityError("NoneSandbox does not allow arbitrary spawn/bash/pi")

    def _target(self, path: Path) -> Path:
        target = path if path.is_absolute() else self.root / path
        return target.resolve()

    def _authorize(self, path: Path) -> None:
        if not any(path.is_relative_to(root) for root in self.authorized_roots):
            raise SandboxCapabilityError(f"Path is outside authorized roots: {path}")

    def _shadow_path(self, target: Path) -> Path:
        if target.is_relative_to(self.root):
            relative = target.relative_to(self.root)
            result = self.shadow / relative
        else:
            for index, root in enumerate(self.authorized_roots[1:], 1):
                if target.is_relative_to(root):
                    result = self.shadow / "_external" / str(index) / target.relative_to(root)
                    break
            else:
                raise SandboxCapabilityError("Path is outside authorized roots")
        self._logical[result] = target
        return result

    def _tombstone(self, target: Path) -> Path:
        return self._shadow_path(target).with_name(target.name + ".weft-deleted")

    def read_file(self, path: Path) -> bytes:
        target = self._target(path)
        self._authorize(target)
        shadow = self._shadow_path(target)
        if self._tombstone(target).exists():
            raise FileNotFoundError(target)
        if shadow.is_file():
            return shadow.read_bytes()
        return target.read_bytes()

    def write_file(self, path: Path, data: bytes) -> None:
        target = self._target(path)
        self._authorize(target)
        shadow = self._shadow_path(target)
        shadow.parent.mkdir(parents=True, exist_ok=True)
        temporary = shadow.with_name(shadow.name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(shadow)
        self._tombstone(target).unlink(missing_ok=True)

    def edit_file(self, path: Path, old_string: str, new_string: str) -> None:
        text = self.read_file(path).decode("utf-8")
        if text.count(old_string) != 1:
            raise ValueError("edit old_string must match exactly once")
        self.write_file(path, text.replace(old_string, new_string, 1).encode("utf-8"))

    def delete_file(self, path: Path) -> None:
        target = self._target(path)
        self._authorize(target)
        self._shadow_path(target).unlink(missing_ok=True)
        tombstone = self._tombstone(target)
        self._logical[tombstone] = target
        tombstone.parent.mkdir(parents=True, exist_ok=True)
        tombstone.write_text("deleted", encoding="utf-8")

    def list_dir(self, path: Path, pattern: str | None = None) -> list[SandboxEntry]:
        target = self._target(path)
        self._authorize(target)
        entries: dict[str, SandboxEntry] = {}
        if target.is_dir():
            for item in target.iterdir():
                entries[item.name] = SandboxEntry(
                    str(item), item.name, item.is_dir(), item.stat().st_size
                )
        shadow = self._shadow_path(target)
        if shadow.is_dir():
            for item in shadow.iterdir():
                if item.name.endswith(".weft-deleted"):
                    entries.pop(item.name[: -len(".weft-deleted")], None)
                    continue
                logical = self._logical.get(item, item)
                entries[item.name] = SandboxEntry(
                    str(logical), item.name, item.is_dir(), item.stat().st_size
                )
        return sorted(
            (
                entry
                for entry in entries.values()
                if not pattern or fnmatch.fnmatch(entry.name, pattern)
            ),
            key=lambda entry: entry.name,
        )

    def collect_changes(self) -> ChangeSet:
        changes: list[Change] = []
        for source in self.shadow.rglob("*"):
            if source.name.endswith((".tmp", ".weft-deleted")) or not source.is_file():
                continue
            target = self._logical.get(source)
            if target is None:
                self._shadow_path(self.root / source.relative_to(self.shadow))
                target = self._logical[source]
            baseline_hash = self.baseline.get(target)
            current_hash = file_hash(source)
            if current_hash == baseline_hash:
                continue
            data = source.read_bytes()
            try:
                text = len(data) <= 1024 * 1024 and data.decode("utf-8") is not None
            except UnicodeDecodeError:
                text = False
            changes.append(
                Change(
                    path=str(target),
                    rel_root=relative_to_root(target, self.root),
                    kind="created" if baseline_hash is None else "modified",
                    size=len(data),
                    is_text=text,
                    protected=protected_path(target, self.root),
                    baseline_hash=baseline_hash,
                    source=source,
                )
            )
        for source in self.shadow.rglob("*.weft-deleted"):
            target = self._logical.get(source)
            if target is None:
                continue
            baseline_hash = self.baseline.get(target)
            if baseline_hash is None:
                continue
            changes.append(
                Change(
                    path=str(target),
                    rel_root=relative_to_root(target, self.root),
                    kind="deleted",
                    size=0,
                    is_text=False,
                    protected=protected_path(target, self.root),
                    baseline_hash=baseline_hash,
                    source=source,
                )
            )
        from weft.sandbox.review import detect_renames

        result = detect_renames(ChangeSet(self.run_id, "none", changes))
        result.authorized_roots = [str(path) for path in self.authorized_roots[1:]]
        path = self.root / ".runs" / self.run_id / "changes.json"
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result

    def apply(self, changes: list[Change], overwrite_conflicts: bool = False) -> list[Change]:
        raise SandboxCapabilityError("NoneSandbox applies changes only through the review flow")

    def discard(self) -> None:
        result = self.collect_changes()
        for change in result.changes:
            if change.state == "pending":
                change.state = "discarded"
        path = self.root / ".runs" / self.run_id / "changes.json"
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        shutil.rmtree(self.shadow, ignore_errors=True)


def create_sandbox(
    root: Path,
    run_id: str,
    mode: str = "inherit",
    settings: SettingsStore | None = None,
) -> Sandbox:
    settings = settings or SettingsStore()
    config = settings.read().get("sandbox", {})
    mode = config.get("default", "sandboxie") if mode == "inherit" else mode
    if mode == "none":
        if not config.get("allow_none_sandbox", False):
            raise SandboxCapabilityError("NoneSandbox is disabled in settings")
        authorized = [Path(path) for path in config.get("authorized_roots", [])]
        return NoneSandbox(root, run_id, authorized)
    if mode == "sandboxie":
        raise SandboxCapabilityError("Sandboxie backend is not configured")
    raise ValueError(f"Unknown sandbox mode: {mode}")
