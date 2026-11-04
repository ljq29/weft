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


@pytest.mark.benchmark
def test_engine_50_noop_linear_nodes_benchmark(tmp_path: Path) -> None:
    """US-EXE-01/AC-1: measure engine overhead for 50 linear No-op nodes."""
    import asyncio
    from typing import Any

    from weft.engine import Engine
    from weft.nodes.flow import TriggerNode
    from weft.nodes.registry import NodeRegistry
    from weft.workflow import WorkflowDocument
    from weft_sdk import Node, Port

    class NoOpNode(Node):
        type = "user.noop_benchmark"
        category = "user"
        description = "No-op scheduling benchmark"
        inputs = (Port("in", "flow", "Ordering"),)
        outputs = (Port("out", "flow", "Ordering"),)
        params_schema = {"type": "object", "properties": {}}

        def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict:
            return {}

    nodes = [
        {
            "id": "n_00000000",
            "type": "flow.trigger",
            "node_version": 1,
            "name": "Trigger",
            "position": {"x": 0, "y": 0},
            "params": {},
        }
    ]
    nodes.extend(
        {
            "id": f"n_{index:08d}",
            "type": "user.noop_benchmark",
            "node_version": 1,
            "name": f"NoOp {index}",
            "position": {"x": index * 100, "y": 0},
            "params": {},
        }
        for index in range(1, 51)
    )
    edges = [
        {
            "id": f"e_{index:08d}",
            "source": f"n_{index:08d}",
            "sourcePort": "out",
            "target": f"n_{index + 1:08d}",
            "targetPort": "in",
            "order": 0,
        }
        for index in range(1, 50)
    ]
    document = WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_0123456789ab",
            "name": "performance",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": nodes,
            "edges": edges,
        }
    )
    registry = NodeRegistry()
    registry.register(TriggerNode)
    registry.register(NoOpNode)
    engine = Engine()
    started = time.perf_counter()
    try:
        record = asyncio.run(engine.run(engine.prepare(document, tmp_path, registry)))
    finally:
        engine.close()
    elapsed = time.perf_counter() - started
    assert record.status == "succeeded"
    assert len(record.nodes) == 51
    report = {
        "nodes": 50,
        "elapsed_seconds": elapsed,
        "milliseconds_per_node": elapsed * 1000 / 50,
        "environment": {"os": platform.platform(), "python": platform.python_version()},
    }
    output = Path(".test-reports/engine-scheduler-benchmark.json")
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


@pytest.mark.benchmark
def test_ws_status_latency_p95_benchmark() -> None:
    """US-EXE-05/AC-1: measure 50 authenticated WS status pushes and report p95."""
    from fastapi.testclient import TestClient
    from weft.api.app import create_app

    app = create_app(token="benchmark-token")
    samples: list[float] = []
    with TestClient(app, base_url="http://127.0.0.1:7788") as client:
        with client.websocket_connect("/api/ws") as socket:
            socket.send_json({"op": "authenticate", "token": "benchmark-token"})
            socket.send_json({"op": "subscribe", "topics": ["run:r_performance"]})
            assert socket.receive_json()["event"] == "subscribed"
            for index in range(50):
                started = time.perf_counter()
                app.state.bus.publish(
                    {
                        "event": "node.status",
                        "run_id": "r_performance",
                        "node_id": "n_performance",
                        "ts": "benchmark",
                        "data": {"status": "executed", "index": index},
                    }
                )
                event = socket.receive_json()
                assert event["event"] == "node.status"
                assert event["data"]["index"] == index
                samples.append(time.perf_counter() - started)
    samples.sort()
    report = {
        "samples": len(samples),
        "p95_ms": samples[47] * 1000,
        "max_ms": samples[-1] * 1000,
        "environment": {"os": platform.platform(), "python": platform.python_version()},
    }
    output = Path(".test-reports/ws-latency-benchmark.json")
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
