from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weft.engine.cache_key import hash_file
from weft.engine.models import now
from weft.workflow.values import ValueRef


@dataclass(frozen=True)
class CachedOutputs:
    outputs: dict[str, ValueRef]
    activated_ports: list[str] | None


class CacheManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cache_root = root / ".runs" / "cache"

    def load(self, node_id: str, key: str) -> CachedOutputs | None:
        directory = self.cache_root / node_id
        meta_path = directory / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["key"] != key:
                return None
            outputs = {
                port: ValueRef.model_validate(value) for port, value in meta["outputs"].items()
            }
            for value in outputs.values():
                if value.path is not None:
                    path = self.root / value.path
                    if not path.is_file() or hash_file(path) != value.hash:
                        return None
            return CachedOutputs(outputs, meta.get("activated_ports"))
        except (OSError, KeyError, ValueError, TypeError):
            return None

    def store(
        self,
        node_id: str,
        key: str,
        outputs: dict[str, ValueRef],
        activated_ports: list[str] | None,
    ) -> None:
        directory = self.cache_root / node_id
        directory.mkdir(parents=True, exist_ok=True)
        stored: dict[str, ValueRef] = {}
        for port, value in outputs.items():
            if value.path is None:
                stored[port] = value
                continue
            source = value.path if value.path.is_absolute() else self.root / value.path
            destination = directory / f"{port}{source.suffix or '.json'}"
            shutil.copyfile(source, destination)
            stored[port] = value.model_copy(update={"path": destination.relative_to(self.root)})
        meta = {
            "key": key,
            "written_at": now(),
            "last_used": now(),
            "outputs": {port: value.model_dump(mode="json") for port, value in stored.items()},
            "activated_ports": activated_ports,
        }
        (directory / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def materialize(
        self, run_root: Path, node_id: str, outputs: dict[str, ValueRef]
    ) -> dict[str, ValueRef]:
        result: dict[str, ValueRef] = {}
        for port, value in outputs.items():
            if value.path is None:
                result[port] = value
                continue
            source = self.root / value.path
            destination = run_root / "outputs" / node_id / f"{port}{source.suffix}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            result[port] = value.model_copy(update={"path": destination.relative_to(self.root)})
        return result

    def reset(self, node_id: str) -> None:
        shutil.rmtree(self.cache_root / node_id, ignore_errors=True)

    def reset_all(self) -> None:
        shutil.rmtree(self.cache_root, ignore_errors=True)

    def enforce_lru(self, max_bytes: int) -> None:
        entries: list[tuple[str, Path, int]] = []
        for directory in self.cache_root.glob("n_*"):
            if not directory.is_dir():
                continue
            try:
                meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
                last_used = meta["last_used"]
            except (OSError, KeyError, ValueError):
                last_used = ""
            size = sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
            entries.append((last_used, directory, size))
        entries.sort(key=lambda item: item[0])
        total = sum(item[2] for item in entries)
        for _, directory, size in entries:
            if total <= max_bytes:
                break
            shutil.rmtree(directory)
            total -= size

    def touch(self, node_id: str) -> None:
        path = self.cache_root / node_id / "meta.json"
        if not path.exists():
            return
        meta: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        meta["last_used"] = now()
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
