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


def run_via_service(
    root: Path, overrides: dict[str, Any], wait: bool, json_output: bool = False
) -> int | None:
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
    if wait and not json_output:
        for node_id, node in record["nodes"].items():
            print(f"{node_id}: {node['status']}")
    if json_output:
        print(json.dumps(record, ensure_ascii=False))
    return {"succeeded": 0, "failed": 1, "cancelled": 2}.get(record["status"], 1)


def run_workflow(path: Path, variables: list[str], wait: bool, json_output: bool = False) -> int:
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
    service_result = run_via_service(root, overrides, wait, json_output)
    if service_result is not None:
        return service_result
    environment.sync()
    registry = builtin_registry()
    registry.load_directory(root / "nodes")
    from weft.agent.client import LLMClient
    from weft.agent.node_tool import NodeTool, validate_node_tools
    from weft.agent.proxy import LLMProxy
    from weft.agent.sandbox_tools import SandboxManager
    from weft.agent.settings import SettingsStore
    from weft.excel import ExcelWorkerSupervisor

    excel_worker = ExcelWorkerSupervisor()
    llm_client = LLMClient(LLMProxy(SettingsStore()))
    engine = Engine(
        lambda root, run_id: WorkerPool(environment, run_id),
        excel_worker=excel_worker,
        llm_client=llm_client,
    )
    sandbox_manager = SandboxManager()
    engine.sandbox_manager = sandbox_manager
    engine.node_tool_factory = lambda prepared, descriptor, agent_node: (
        NodeTool(prepared, engine, descriptor, agent_node)
        if descriptor.get("kind") == "node"
        else (
            sandbox_manager.create(prepared, descriptor, agent_node)
            if descriptor.get("kind") == "sandboxed"
            else sandbox_manager.get(prepared, descriptor["binding"]["sandbox"])
        )
    )
    document = WorkflowStore(root).load()
    validate_node_tools(document, registry)
    from weft.workflow.resources import preflight_resources

    report = asyncio.run(preflight_resources(document, root, registry, engine, overrides))
    if report["missing"]:
        engine.close()
        raise ValueError(f"外部资源缺失：{report['missing']}")
    prepared = engine.prepare(
        document,
        root,
        registry,
        trigger={"source": "manual", "ts": "", "payload": {"overrides": overrides}},
    )
    try:
        with ExecutionLock(root, prepared.record.run_id).acquire():
            record = asyncio.run(engine.run(prepared))
    finally:
        engine.close()
    from weft.workflow.history import RunHistory

    RunHistory(root).cleanup(SettingsStore().read().get("cache", {}).get("run_retention", 50))
    if wait and not json_output:
        for node_id, node in record.nodes.items():
            print(f"{node_id}: {node.status}")
    if json_output:
        print(json.dumps(record.to_dict(), ensure_ascii=False))
    return {"succeeded": 0, "failed": 1, "cancelled": 2}.get(record.status, 1)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weft", description="Local-first visual workflows")
    parser.add_argument("--version", action="store_true", help="show the service version")
    subparsers = parser.add_subparsers(dest="command")
    run = subparsers.add_parser("run", help="run a workflow")
    run.add_argument("path", type=Path)
    run.add_argument("--var", action="append", default=[])
    run.add_argument("--wait", action="store_true")
    run.add_argument("--json", action="store_true")
    serve = subparsers.add_parser("serve", help="start the local service")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--no-triggers", action="store_true")
    serve.add_argument("--json", action="store_true")
    pack = subparsers.add_parser("pack", help="pack a portable workflow")
    pack.add_argument("path", type=Path)
    pack.add_argument("-o", "--output", type=Path)
    pack.add_argument("--exclude-data", action="store_true")
    pack.add_argument("--confirm-warnings", action="store_true")
    pack.add_argument("--json", action="store_true")
    unpack = subparsers.add_parser("unpack", help="import a packed workflow")
    unpack.add_argument("path", type=Path)
    unpack.add_argument("-d", "--dest-dir", type=Path, required=True)
    unpack.add_argument("--json", action="store_true")
    doctor = subparsers.add_parser("doctor", help="check local runtime and clean owned leftovers")
    doctor.add_argument("--cleanup", action="store_true")
    doctor.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(f"weft {__version__}")
        return 0
    if args.command == "run":
        return run_workflow(args.path, args.var, args.wait, args.json)
    if args.command == "serve":
        import socket

        import uvicorn

        from weft.agent.settings import SettingsStore
        from weft.api.app import create_app

        server = SettingsStore().read()["server"]
        host = args.host or server["host"]
        port = args.port or server["port"]
        try:
            with socket.socket() as sock:
                sock.bind((host, port))
        except OSError as exception:
            print(f"端口 {host}:{port} 不可用：{exception}；请使用 --port")
            return 1
        application = create_app(host=host, port=port, enable_triggers=not args.no_triggers)
        if args.json:
            print(json.dumps({"status": "started", "host": host, "port": port}))
        if not args.no_browser:
            webbrowser.open(f"http://{host}:{port}/?token={application.state.session.token}")
        try:
            uvicorn.run(application, host=host, port=port)
        except OSError as exception:
            print(f"服务启动失败：{exception}；请使用 --port")
            return 1
        return 0
    if args.command == "doctor":
        from weft.doctor import run_doctor

        report = run_doctor(args.cleanup)
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            for check in report["checks"]:
                print(f"{check['status']} {check['name']}: {check['message']}")
            for message in report["cleanup"]:
                print(message)
        return int(report["fail_count"])
    if args.command == "pack":
        from weft.workflow.packaging import PackError, pack_workflow

        try:
            path = pack_workflow(args.path, args.output, args.exclude_data, args.confirm_warnings)
        except PackError as exception:
            print(json.dumps(exception.report.as_dict(), ensure_ascii=False))
            return 1
        print(json.dumps({"path": str(path)}) if args.json else str(path))
        return 0
    if args.command == "unpack":
        from weft.workflow.packaging import unpack_workflow

        root = unpack_workflow(args.path, args.dest_dir)
        from weft.workflow import WorkflowStore

        result = {"id": WorkflowStore(root).load().id, "path": str(root)}
        print(json.dumps(result) if args.json else str(root))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
