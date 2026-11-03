from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError
from weft.engine.cache_key import (
    CacheKeyInput,
    ExternalInput,
    build_cache_key,
    hash_external_input,
)
from weft.workflow import PortType, ValueRef, is_compatible


@pytest.mark.parametrize("source", list(PortType))
@pytest.mark.parametrize("target", list(PortType))
def test_complete_port_compatibility_matrix(source: PortType, target: PortType) -> None:
    """US-DES-03/AC-5: all 36 port combinations follow the documented matrix."""
    expected = source == target or (
        target == PortType.FLOW and source not in {PortType.TOOL, PortType.FLOW}
    )
    assert is_compatible(source, target) is expected


def cache_input() -> CacheKeyInput:
    return CacheKeyInput(
        node_type="table.row_filter",
        node_version=1,
        implementation_hash="sha256:implementation",
        resolved_params={"operator": ">", "value": 10},
        input_hashes=(("in", "sha256:input"),),
        external_input_hashes=(),
        user_code_hash="sha256:code",
        uv_lock_hash="sha256:lock",
        iteration_index=None,
    )


def test_cache_key_is_deterministic_and_covers_every_input() -> None:
    """US-EXE-04/AC-2: canonical params and every declared component determine the cache key."""
    first = cache_input()
    reordered = cache_input()
    reordered.resolved_params = {"value": 10, "operator": ">"}
    assert build_cache_key(first) == build_cache_key(reordered)
    for field, value in (
        ("node_type", "table.sorter"),
        ("node_version", 2),
        ("implementation_hash", "sha256:changed"),
        ("resolved_params", {"operator": ">=", "value": 10}),
        ("input_hashes", (("in", "sha256:changed"),)),
        ("external_input_hashes", (("path", "sha256:directory"),)),
        ("user_code_hash", "sha256:changed"),
        ("uv_lock_hash", "sha256:changed"),
        ("iteration_index", 0),
    ):
        changed = cache_input()
        setattr(changed, field, value)
        assert build_cache_key(changed) != build_cache_key(first)


def test_file_cache_input_uses_content_not_mtime_or_size(tmp_path: Path) -> None:
    """US-EXE-04/AC-2: file hashing detects equal-size content changes with preserved mtime."""
    path = tmp_path / "data.csv"
    path.write_bytes(b"aaa")
    stat = path.stat()
    external = ExternalInput(name="path", kind="file", path=path)
    before = hash_external_input(external)
    path.write_bytes(b"bbb")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    after = hash_external_input(external)
    assert before != after


def test_directory_cache_input_is_sorted_and_detects_entry_changes(tmp_path: Path) -> None:
    """US-EXE-04/AC-2: directory fingerprints use sorted path and metadata entries."""
    (tmp_path / "b.xlsx").write_bytes(b"b")
    (tmp_path / "a.xlsx").write_bytes(b"a")
    (tmp_path / "ignore.txt").write_bytes(b"ignored")
    external = ExternalInput(
        name="path", kind="directory", path=tmp_path, pattern="*.xlsx", recursive=False
    )
    before = hash_external_input(external)
    (tmp_path / "c.xlsx").write_bytes(b"c")
    assert hash_external_input(external) != before


def test_value_ref_json_inline_threshold_and_large_file(tmp_path: Path) -> None:
    """T1.2: small JSON is inline and large JSON is stored as a hashed file value."""
    small = ValueRef.from_json({"value": 1})
    assert small.inline == {"value": 1}
    assert small.path is None
    large = ValueRef.from_json({"value": "x" * 300_000}, directory=tmp_path)
    assert large.inline is None
    assert large.path is not None
    assert json.loads(large.path.read_text(encoding="utf-8"))["value"] == "x" * 300_000


def test_value_ref_requires_location_and_table_shape() -> None:
    """T1.2: ValueRef validates its discriminated storage and table metadata."""
    with pytest.raises(ValidationError):
        ValueRef.model_validate({"kind": "json", "hash": "sha256:x"})
    with pytest.raises(ValidationError):
        ValueRef.model_validate({"kind": "table", "path": "x.arrow", "hash": "sha256:x"})
