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


@pytest.mark.benchmark
def test_real_service_cold_start_benchmark(tmp_path: Path) -> None:
    """US-SET-02/AC-1; US-SET-04/AC-1: measure real serve until health and version are ready."""
    import socket
    import subprocess
    import sys
    import urllib.request

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = tmp_path / "config"
    environment = dict(os.environ)
    environment["WEFT_CONFIG_DIR"] = str(config)
    started = time.perf_counter()
    process = subprocess.Popen(
        [sys.executable, "-m", "weft", "serve", "--no-browser", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    try:
        for _ in range(500):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=0.1
                ) as response:
                    assert response.status == 200
                    break
            except OSError:
                time.sleep(0.02)
        else:
            raise AssertionError("service did not start")
        session = json.loads((config / "session.json").read_text(encoding="utf-8"))
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/system/version",
            headers={"Authorization": f"Bearer {session['token']}"},
        )
        with urllib.request.urlopen(request, timeout=1) as response:
            assert json.loads(response.read())["version"] == "0.3.0"
        elapsed = time.perf_counter() - started
    finally:
        process.terminate()
        process.wait(timeout=10)
    report = {
        "cold_start_seconds": elapsed,
        "health_status": 200,
        "version_status": 200,
        "environment": {"os": platform.platform(), "python": platform.python_version()},
    }
    output = Path(".test-reports/service-cold-start-benchmark.json")
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


@pytest.mark.benchmark
def test_pure_cache_materialization_100k_by_20_benchmark(tmp_path: Path) -> None:
    """US-EXE-04/AC-5: measure cached 100,000×20 output copy, hash reuse and disk growth."""
    from weft.engine.cache import CacheManager
    from weft.workflow.values import ValueRef

    table = pa.Table.from_arrays(
        [pa.array([row * 20 + column for row in range(100_000)]) for column in range(20)],
        names=[f"c{column}" for column in range(20)],
    )
    source_path = tmp_path / "source.arrow"
    with pa.ipc.new_file(source_path, table.schema) as writer:
        writer.write_table(table)
    digest = hash_file(source_path)
    reference = ValueRef(
        kind="table",
        path=source_path,
        hash=digest,
        rows=100_000,
        cols=20,
    )
    manager = CacheManager(tmp_path)
    manager.store("n_00000001", "benchmark", {"out": reference}, None)
    cached = manager.load("n_00000001", "benchmark")
    assert cached is not None

    run_root = tmp_path / ".runs" / "r_cache_benchmark"
    started = time.perf_counter()
    materialized = manager.materialize(run_root, "n_00000001", cached.outputs)
    copy_seconds = time.perf_counter() - started
    output_ref = materialized["out"]
    assert output_ref.path is not None
    output_path = tmp_path / output_ref.path
    assert output_path.is_file()
    assert output_ref.hash == digest
    with pa.memory_map(str(output_path)) as source:
        restored = pa.ipc.open_file(source).read_all()
    assert restored.num_rows == 100_000 and restored.num_columns == 20
    output_files = [path for path in run_root.rglob("*") if path.is_file()]
    disk_increment = sum(path.stat().st_size for path in output_files)
    report = {
        "rows": 100_000,
        "cols": 20,
        "copy_seconds": copy_seconds,
        "disk_increment_bytes": disk_increment,
        "source_bytes": source_path.stat().st_size,
        "hash_reused": output_ref.hash == digest,
        "environment": {"os": platform.platform(), "python": platform.python_version()},
    }
    output = Path(".test-reports/cache-materialize-benchmark.json")
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
