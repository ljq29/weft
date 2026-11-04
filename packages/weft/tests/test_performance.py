from __future__ import annotations

import ctypes
import json
import os
import platform
import time
from pathlib import Path

import polars as pl
import pyarrow as pa
import pytest
from weft.engine.cache_key import hash_file


def physical_memory_gib() -> float:
    if os.name == "nt":
        value = ctypes.c_ulonglong()
        if not ctypes.WinDLL("kernel32").GetPhysicallyInstalledSystemMemory(ctypes.byref(value)):
            raise OSError("Cannot read physical memory")
        return value.value / 1024**2
    return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3


@pytest.mark.benchmark
def test_arrow_worker_ipc_100k_by_20_staged_benchmark(tmp_path: Path) -> None:
    """US-TBL-01/AC-2: record each Arrow IPC stage for 100,000 rows by 20 columns."""
    table = pa.Table.from_arrays(
        [pa.array([row * 20 + column for row in range(100_000)]) for column in range(20)],
        names=[f"c{column}" for column in range(20)],
    )

    started = time.perf_counter()
    buffer = pa.BufferOutputStream()
    with pa.ipc.new_file(buffer, table.schema) as writer:
        writer.write_table(table)
    payload = buffer.getvalue().to_pybytes()
    serialize_seconds = time.perf_counter() - started

    path = tmp_path / "table.arrow"
    started = time.perf_counter()
    path.write_bytes(payload)
    write_seconds = time.perf_counter() - started

    started = time.perf_counter()
    digest = hash_file(path)
    hash_seconds = time.perf_counter() - started

    started = time.perf_counter()
    with pa.memory_map(str(path)) as source:
        restored = pa.ipc.open_file(source).read_all()
    map_seconds = time.perf_counter() - started

    started = time.perf_counter()
    frame = pl.from_arrow(restored)
    convert_seconds = time.perf_counter() - started

    assert frame.shape == (100_000, 20)
    assert frame.row(100_000 - 1)[19] == 99_999 * 20 + 19
    assert len(digest) == 71
    stages = {
        "serialize_seconds": serialize_seconds,
        "write_seconds": write_seconds,
        "hash_seconds": hash_seconds,
        "map_seconds": map_seconds,
        "convert_seconds": convert_seconds,
    }
    report = {
        "rows": 100_000,
        "cols": 20,
        "cache": "cold",
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "pyarrow": pa.__version__,
            "polars": pl.__version__,
            "cpu": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "ram_gib": physical_memory_gib(),
        },
        **stages,
        "total_seconds": sum(stages.values()),
    }
    output = Path(".test-reports/arrow-worker-benchmark.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
