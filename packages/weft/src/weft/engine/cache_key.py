from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from weft.workflow.values import canonical_json_bytes, content_hash


@dataclass
class CacheKeyInput:
    node_type: str
    node_version: int
    implementation_hash: str
    resolved_params: dict[str, Any]
    input_hashes: tuple[tuple[str, str], ...]
    external_input_hashes: tuple[tuple[str, str], ...]
    user_code_hash: str
    uv_lock_hash: str
    iteration_index: int | None


@dataclass(frozen=True)
class ExternalInput:
    name: str
    kind: Literal["file", "directory"]
    path: Path
    pattern: str = "*"
    recursive: bool = False


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def directory_fingerprint(path: Path, pattern: str, recursive: bool) -> str:
    paths = path.rglob("*") if recursive else path.glob("*")
    entries = []
    for item in paths:
        if not item.match(pattern):
            continue
        stat = item.stat()
        entries.append(
            {
                "path": item.relative_to(path).as_posix(),
                "name": item.name,
                "size": stat.st_size,
                "modified": stat.st_mtime_ns,
                "is_dir": item.is_dir(),
            }
        )
    entries.sort(key=lambda entry: str(entry["path"]))
    return content_hash(canonical_json_bytes(entries))


def hash_external_input(external: ExternalInput) -> str:
    if external.kind == "file":
        return hash_file(external.path)
    return directory_fingerprint(external.path, external.pattern, external.recursive)


def build_cache_key(value: CacheKeyInput) -> str:
    components = [
        value.node_type,
        value.node_version,
        value.implementation_hash,
        value.resolved_params,
        sorted(value.input_hashes),
        sorted(value.external_input_hashes),
        value.user_code_hash,
        value.uv_lock_hash,
        value.iteration_index,
    ]
    return content_hash(canonical_json_bytes(components))
