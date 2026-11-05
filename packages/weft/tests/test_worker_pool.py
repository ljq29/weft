from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pyarrow as pa
import pytest
from weft.worker import (
    EnvironmentError,
    WorkerCrashedError,
    WorkerPool,
    WorkerVersionError,
    WorkflowEnvironment,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def make_workflow(root: Path, worker_version: str = "0.2.1") -> None:
    (root / "nodes").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'''[project]
name = "worker-fixture"
version = "0.2.1"
requires-python = ">=3.12"
dependencies = ["weft-worker=={worker_version}", "polars", "pyarrow"]

[tool.uv.sources]
weft-worker = {{ path = "{(PROJECT_ROOT / "packages/weft-worker").as_posix()}" }}
weft-sdk = {{ path = "{(PROJECT_ROOT / "packages/weft-sdk").as_posix()}" }}
''',
        encoding="utf-8",
    )
    (root / "nodes" / "slow.py").write_text(
        """import os
import time
import polars as pl
from weft_sdk import Node, Port, node

@node
class SlowNode(Node):
    type = "user.slow"
    category = "user"
    description = "Slow integration fixture"
    outputs = (Port("out", "variable", "Result"), Port("table", "table", "Table"))
    calls = 0
    def execute(self, ctx, inputs, params):
        type(self).calls += 1
        deadline = time.monotonic() + params.get("delay", 0.1)
        while time.monotonic() < deadline:
            ctx.check_cancelled()
            time.sleep(0.01)
        table = pl.DataFrame({"value": [1, 2, 3]})
        result = {"pid": os.getpid(), "run_id": ctx.run_id, "calls": type(self).calls}
        return {"out": result, "table": table}
""",
        encoding="utf-8",
    )


@pytest.fixture
def workflow_env(tmp_path: Path) -> WorkflowEnvironment:
    make_workflow(tmp_path)
    env = WorkflowEnvironment(tmp_path, service_version="0.2.1")
    env.sync()
    return env


@pytest.mark.integration
def test_real_worker_pool_parallel_arrow_isolation_and_shutdown(
    workflow_env: WorkflowEnvironment,
) -> None:
    """US-EXE-14/AC-1,2,3,5,6: real venv workers run in parallel without PYTHONPATH."""

    async def scenario() -> None:
        pool = WorkerPool(workflow_env, "r_first", size=2)
        assert pool.process_ids == []
        pool.start()
        started = time.perf_counter()
        first, second = await asyncio.gather(
            pool.execute("exec_1", "user.slow", {"delay": 0.2}, {}),
            pool.execute("exec_2", "user.slow", {"delay": 0.2}, {}),
        )
        elapsed = time.perf_counter() - started
        assert elapsed < 0.38
        assert first["outputs"]["out"]["inline"]["run_id"] == "r_first"
        assert second["outputs"]["out"]["inline"]["pid"] != first["outputs"]["out"]["inline"]["pid"]
        table_ref = first["outputs"]["table"]
        with pa.memory_map(str(table_ref["path"])) as source:
            assert pa.ipc.open_file(source).read_all().column("value").to_pylist() == [1, 2, 3]
        assert "PYTHONPATH" not in pool.worker_env
        process_ids = pool.process_ids
        pool.close()
        assert not workflow_env.process_alive(process_ids)
        second_pool = WorkerPool(workflow_env, "r_second", size=1)
        result = await second_pool.execute("exec_3", "user.slow", {"delay": 0}, {})
        assert result["outputs"]["out"]["inline"]["calls"] == 1
        assert result["outputs"]["out"]["inline"]["run_id"] == "r_second"
        second_pool.close()

    asyncio.run(scenario())


@pytest.mark.integration
def test_worker_cooperative_cancellation(workflow_env: WorkflowEnvironment) -> None:
    """US-EXE-08/AC-2, US-TBL-08/AC-7: user code receives worker cancellation."""

    async def scenario() -> None:
        pool = WorkerPool(workflow_env, "r_cancel", size=1)
        pool.start()
        task = asyncio.create_task(pool.execute("exec_cancel", "user.slow", {"delay": 10}, {}))
        await asyncio.sleep(0.15)
        await pool.cancel("exec_cancel")
        result = await task
        assert result["error"]["type"] == "Cancelled"
        pool.close()

    asyncio.run(scenario())


@pytest.mark.integration
def test_worker_version_mismatch_is_rejected(tmp_path: Path) -> None:
    """US-EXE-14/AC-5,7: service and worker versions must match exactly before execution."""
    make_workflow(tmp_path, worker_version="9.9.9")
    env = WorkflowEnvironment(tmp_path, service_version="0.2.1")
    with pytest.raises(WorkerVersionError, match="weft-worker==9.9.9"):
        env.sync()


@pytest.mark.integration
def test_explicit_worker_update_relocks_and_syncs(tmp_path: Path) -> None:
    """US-EXE-14/AC-7: an explicit update changes the dependency and produces a usable worker."""
    make_workflow(tmp_path, worker_version="9.9.9")
    env = WorkflowEnvironment(tmp_path, service_version="0.2.1")
    env.update_worker()
    assert "weft-worker==0.2.1" in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert (tmp_path / "uv.lock").is_file()
    assert env.python.is_file()


@pytest.mark.integration
def test_uv_failure_contains_complete_output(tmp_path: Path) -> None:
    """US-EXE-14/AC-4: dependency failures expose uv stdout and stderr."""
    make_workflow(tmp_path)
    path = tmp_path / "pyproject.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '"weft-worker==0.2.1",', '"weft-worker==0.2.1", "missing-local",'
        )
        + '\n[tool.uv.sources.missing-local]\npath = "missing-local-package"\n',
        encoding="utf-8",
    )
    with pytest.raises(EnvironmentError, match="missing-local-package") as error:
        WorkflowEnvironment(tmp_path).sync()
    assert "error" in str(error.value)


def test_pool_defaults_to_four_lazy_workers(tmp_path: Path) -> None:
    """US-EXE-14/AC-3: the default pool is lazy and has four slots."""
    pool = WorkerPool(WorkflowEnvironment(tmp_path), "r_lazy")
    assert pool.size == 4
    assert pool.process_ids == []


@pytest.mark.integration
def test_worker_crash_fails_request_and_cleans_up(workflow_env: WorkflowEnvironment) -> None:
    """US-EXE-14/AC-3: a crashed worker fails its request and the run pool cleans up."""

    async def scenario() -> None:
        pool = WorkerPool(workflow_env, "r_crash", size=1)
        pool.start()
        pool.workers[0].process.terminate()
        process_ids = pool.process_ids
        with pytest.raises(WorkerCrashedError):
            await pool.execute("exec_crash", "user.slow", {"delay": 0}, {})
        pool.close()
        assert not workflow_env.process_alive(process_ids)

    asyncio.run(scenario())


def test_workflow_uv_ignores_host_project_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-EXE-14/AC-1: workflow sync never inherits the host UV_PROJECT_ENVIRONMENT."""
    from types import SimpleNamespace

    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", ".venv-host")
    captured: dict = {}

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("weft.worker.environment.subprocess.run", run)
    WorkflowEnvironment(tmp_path).run_uv("sync")
    environment = captured["env"]
    assert "UV_PROJECT_ENVIRONMENT" not in environment
