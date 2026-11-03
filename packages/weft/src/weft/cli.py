"""Weft command-line interface."""

import argparse
import asyncio
import json
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from weft import __version__


def run_via_service(root: Path, overrides: dict[str, Any], wait: bool) -> int | None:
    from weft.api.security import load_session

    try:
        session = load_session()
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    base = f"http://{session.host}:{session.port}"

    def request(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            base + path,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {session.token}",
            },
            method="POST" if data is not None else "GET",
        )
        with urllib.request.urlopen(req, timeout=0.5 if payload is None else 300) as response:
            result = json.loads(response.read())
            if not isinstance(result, dict):
                raise TypeError("Service response must be an object")
            return result

    try:
        request("/api/system/version")
        opened = request("/api/workflows/open", {"path": str(root)})
        result = request(
            f"/api/workflows/{opened['id']}/runs",
            {"overrides": overrides, "scope": {"kind": "all", "node_id": None}},
        )
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return None
    while True:
        record = request(f"/api/runs/{result['run_id']}")
        if record["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)
    if wait:
        for node_id, node in record["nodes"].items():
            print(f"{node_id}: {node['status']}")
    return {"succeeded": 0, "failed": 1, "cancelled": 2}.get(record["status"], 1)


def run_workflow(path: Path, variables: list[str], wait: bool) -> int:
    from weft.engine import Engine
    from weft.engine.lock import ExecutionLock
    from weft.nodes.registry import builtin_registry
    from weft.worker import WorkflowEnvironment
    from weft.worker.pool import WorkerPool
    from weft.workflow import WorkflowStore

    root = path.resolve()
    environment = WorkflowEnvironment(root)
    overrides: dict[str, Any] = {}
    for item in variables:
        key, separator, value = item.partition("=")
        if not separator:
            raise ValueError("--var 必须使用 name=value")
        try:
            overrides[key] = json.loads(value)
        except json.JSONDecodeError:
            overrides[key] = value
    service_result = run_via_service(root, overrides, wait)
    if service_result is not None:
        return service_result
    environment.sync()
    registry = builtin_registry()
    registry.load_directory(root / "nodes")
    engine = Engine(lambda root, run_id: WorkerPool(environment, run_id))
    prepared = engine.prepare(
        WorkflowStore(root).load(),
        root,
        registry,
        trigger={"source": "manual", "ts": "", "payload": {"overrides": overrides}},
    )
    with ExecutionLock(root, prepared.record.run_id).acquire():
        record = asyncio.run(engine.run(prepared))
    if wait:
        for node_id, node in record.nodes.items():
            print(f"{node_id}: {node.status}")
    return {"succeeded": 0, "failed": 1, "cancelled": 2}.get(record.status, 1)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weft", description="Local-first visual workflows")
    parser.add_argument("--version", action="store_true", help="show the service version")
    subparsers = parser.add_subparsers(dest="command")
    run = subparsers.add_parser("run", help="run a workflow")
    run.add_argument("path", type=Path)
    run.add_argument("--var", action="append", default=[])
    run.add_argument("--wait", action="store_true")
    serve = subparsers.add_parser("serve", help="start the local service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7788)
    serve.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(f"weft {__version__}")
        return 0
    if args.command == "run":
        return run_workflow(args.path, args.var, args.wait)
    if args.command == "serve":
        import uvicorn

        from weft.api.app import create_app

        if not args.no_browser:
            webbrowser.open(f"http://{args.host}:{args.port}")
        uvicorn.run(create_app(), host=args.host, port=args.port)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
