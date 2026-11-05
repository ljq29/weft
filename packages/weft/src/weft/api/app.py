from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi import Path as RoutePath
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from weft import __version__
from weft.api.events import EventBus
from weft.api.security import Session, config_dir, create_session
from weft.engine import Engine, RunCoordinator
from weft.engine.cache import CacheManager
from weft.nodes.registry import builtin_registry
from weft.worker import WorkflowEnvironment
from weft.worker.pool import WorkerPool
from weft.workflow import WorkflowDocument, WorkflowStore, validate_workflow


class OpenRequest(BaseModel):
    path: str


class CreateRequest(BaseModel):
    name: str
    parent_dir: str


class RunRequest(BaseModel):
    scope: dict[str, Any] | None = None
    overrides: dict[str, Any] = {}
    allow_missing_resources: bool = False


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatClearRequest(BaseModel):
    clear_memory: bool = False


class ConfirmRequest(BaseModel):
    request_id: str
    decision: str
    modified_args: dict[str, Any] | None = None


class ChangeApplyRequest(BaseModel):
    paths: list[str]
    overwrite_conflicts: bool = False


class ChangeDiscardRequest(BaseModel):
    paths: list[str] | None = None


class BrowseRequest(BaseModel):
    path: str
    dirs_only: bool = False


class PackRequest(BaseModel):
    exclude_data: bool = False
    confirm_warnings: bool = False
    output: str | None = None


class UnpackRequest(BaseModel):
    zip_path: str
    dest_dir: str


def create_app(
    token: str | None = None,
    host: str = "127.0.0.1",
    port: int = 7788,
    session: Session | None = None,
    enable_triggers: bool = True,
) -> FastAPI:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        from weft.agent.settings import SettingsStore

        token = token or (session.token if session is not None else "")
        token = token or SettingsStore().read().get("server", {}).get("global_token", "")
        if not token:
            raise ValueError("Non-local listen requires server.global_token")
        import logging

        logging.getLogger("weft").warning("Weft is listening on a non-local host")
    if session is None:
        session = (
            create_session(host, port)
            if token is None
            else Session(token, host, port, config_dir() / "session.json")
        )
    app = FastAPI(title="Weft")
    app.state.session = session
    app.state.roots = {}
    app.state.bus = EventBus()
    from weft.agent.node_tool import NodeTool
    from weft.agent.sandbox_tools import SandboxManager
    from weft.excel import ExcelWorkerSupervisor

    excel_worker = ExcelWorkerSupervisor()
    sandbox_manager = SandboxManager()
    engine = Engine(
        lambda root, run_id: WorkerPool(WorkflowEnvironment(root), run_id),
        excel_worker=excel_worker,
    )
    engine.sandbox_manager = sandbox_manager
    app.state.sandbox = sandbox_manager
    engine.node_tool_factory = lambda prepared, descriptor, agent_node: (
        NodeTool(prepared, engine, descriptor, agent_node)
        if descriptor.get("kind") == "node"
        else (
            sandbox_manager.create(prepared, descriptor, agent_node)
            if descriptor.get("kind") == "sandboxed"
            else sandbox_manager.get(prepared, descriptor["binding"]["sandbox"])
        )
    )
    from weft.agent.confirmation import ConfirmationManager

    confirmations = ConfirmationManager(engine)
    app.state.confirmations = confirmations
    engine.confirmation_handler = lambda request: confirmations.request(
        engine.runs[request["run_id"]], request
    )
    sandbox_manager.confirmation_handler = engine.confirmation_handler
    engine.event_sink = app.state.bus.publish
    app.state.engine = engine
    app.state.excel = excel_worker
    app.router.add_event_handler("shutdown", engine.close)
    app.state.coordinator = RunCoordinator(engine)
    from weft.triggers.chat import ChatSource

    app.state.chat = ChatSource(app.state.coordinator)
    app.state.registry = builtin_registry()
    engine.registry = app.state.registry
    from weft.triggers.http import HttpSource
    from weft.triggers.manager import TriggerManager

    app.state.http = HttpSource(app.state.coordinator)
    app.state.triggers = (
        TriggerManager(app.state.coordinator, app.state.roots) if enable_triggers else None
    )
    engine.trigger_manager = app.state.triggers
    if app.state.triggers is not None:
        app.router.add_event_handler("shutdown", app.state.triggers.close)
    allowed_hosts = (
        {f"{host}:{port}", f"localhost:{port}"} if host == "127.0.0.1" else {f"{host}:{port}"}
    )

    @app.middleware("http")
    async def security(request: Any, call_next: Any) -> Any:
        request.state.trace_id = secrets.token_hex(8)
        request_host = request.headers.get("host", "")
        if request_host not in allowed_hosts:
            return error("FORBIDDEN", "Host 不受信任", 403)
        origin = request.headers.get("origin")
        allowed_origins = {f"http://{item}" for item in allowed_hosts}
        if dev_origin := os.environ.get("WEFT_DEV_ORIGIN"):
            allowed_origins.add(dev_origin)
        if origin and origin not in allowed_origins:
            return error("FORBIDDEN", "Origin 不受信任", 403)
        if request.url.path.startswith("/api") and not (
            request.url.path.startswith("/api/workflows/") and request.url.path.endswith("/trigger")
        ):
            expected = session.token
            if not secrets.compare_digest(
                request.headers.get("authorization", ""), f"Bearer {expected}"
            ):
                return error("UNAUTHORIZED", "令牌缺失或无效", 401)
        response = await call_next(request)
        from weft.operations import log_http

        log_http(
            request.method,
            request.url.path,
            response.status_code,
            request.state.trace_id,
        )
        return response

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/system/version")
    def version() -> dict[str, Any]:
        return {
            "version": __version__,
            "schema_version": 1,
            "host": host,
            "warning": "非本机监听已启用" if host not in {"127.0.0.1", "localhost", "::1"} else "",
        }

    @app.get("/api/system/doctor")
    async def system_doctor() -> Any:
        from weft.doctor import run_doctor

        return await asyncio.to_thread(run_doctor)

    from weft.agent.client import LLMClient
    from weft.agent.proxy import LLMProxy
    from weft.agent.settings import LLMConfigError, SettingsStore

    settings_store = SettingsStore()
    app.state.settings = settings_store
    app.state.coordinator.run_retention = (
        settings_store.read().get("cache", {}).get("run_retention", 50)
    )
    llm_proxy = LLMProxy(settings_store)
    app.state.llm_proxy = llm_proxy
    engine.llm_client = LLMClient(llm_proxy)
    app.state.llm = engine.llm_client
    from weft.operations import configure_service_logging

    configure_service_logging(settings_store.read())

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return settings_store.masked()

    @app.put("/api/settings")
    def update_settings(settings: dict[str, Any]) -> Any:
        try:
            updated = settings_store.update(settings)
            app.state.coordinator.run_retention = updated.get("cache", {}).get("run_retention", 50)
            app.state.excel.call_timeout = updated["excel"]["call_timeout"]
            app.state.excel.restart_after_timeouts = updated["excel"]["restart_after_timeouts"]
            configure_service_logging(updated)
            return updated
        except LLMConfigError as exception:
            return error("INVALID_SETTINGS", str(exception), 400)

    @app.post("/api/settings/llm/{name}/test")
    async def test_llm(name: str) -> Any:
        try:
            return await llm_proxy.test(name)
        except Exception as exception:
            return error("LLM_CONNECTION_FAILED", str(exception), 400)

    @app.post("/api/fs/browse")
    def browse(request: BrowseRequest) -> dict[str, Any]:
        path = Path(request.path).resolve()
        entries = [
            {"name": item.name, "path": str(item), "is_dir": item.is_dir()}
            for item in sorted(path.iterdir())
            if item.is_dir() or not request.dirs_only
        ]
        return {"path": str(path), "entries": entries}

    @app.get("/api/workflows")
    def workflows() -> list[dict[str, Any]]:
        return [
            {
                "id": workflow_id,
                "name": WorkflowStore(root).load().name,
                "path": str(root),
                "dirty": False,
                "env_status": "ok",
            }
            for workflow_id, root in app.state.roots.items()
        ]

    @app.post("/api/workflows", status_code=201)
    def create_workflow(request: CreateRequest) -> Any:
        root = Path(request.parent_dir) / f"{request.name}.weft"
        if root.exists():
            return error("WORKFLOW_EXISTS", "目录已存在", 409)
        for directory in ("data", "nodes", "prompts"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / ".gitignore").write_text(".runs/\n.venv/\n__pycache__/\n", encoding="utf-8")
        now = datetime.now(UTC)
        document = WorkflowDocument.model_validate(
            {
                "schema_version": 1,
                "revision": 1,
                "id": f"wf_{secrets.token_hex(6)}",
                "name": request.name,
                "created_at": now,
                "modified_at": now,
                "nodes": [
                    {
                        "id": "n_00000001",
                        "type": "flow.trigger",
                        "node_version": 1,
                        "name": "Trigger",
                        "position": {"x": 0, "y": 200},
                        "params": {"manual": {"enabled": True}},
                    }
                ],
            }
        )
        (root / "workflow.json").write_text(document.model_dump_json(indent=2), encoding="utf-8")
        (root / "pyproject.toml").write_text(
            f'[project]\nname = "{request.name}"\nversion = "0.0.0"\n'
            f'requires-python = ">=3.12"\n'
            f'dependencies = ["weft-worker=={__version__}"]\n',
            encoding="utf-8",
        )
        app.state.roots[document.id] = root
        return {"id": document.id, "path": str(root)}

    @app.post("/api/workflows/open")
    async def open_workflow(request: OpenRequest) -> dict[str, Any]:
        root = Path(request.path).resolve()
        WorkflowEnvironment(root).sync()
        document = WorkflowStore(root).load()
        app.state.roots[document.id] = root
        if app.state.triggers is not None:
            app.state.triggers.activate(document, root)
        return {"id": document.id, "path": str(root), "env_status": "ok"}

    @app.get("/api/workflows/{workflow_id}")
    def get_workflow(workflow_id: str) -> Any:
        return WorkflowStore(root_for(app, workflow_id)).load().model_dump(mode="json")

    @app.put("/api/workflows/{workflow_id}")
    async def put_workflow(workflow_id: str, document: WorkflowDocument, request: Request) -> Any:
        if request.headers.get("x-weft-client") != "ui":
            return error("FORBIDDEN", "缺少 UI 操作标记", 403)
        from weft.agent.node_tool import validate_node_tools
        from weft.triggers.manager import validate_trigger_config

        try:
            validate_trigger_config(document)
            validate_node_tools(document, app.state.registry)
        except (ValueError, PermissionError) as exc:
            return error("NODE_TOOL_NOT_AUTHORIZED", str(exc), 400)
        root = root_for(app, workflow_id)
        try:
            saved = WorkflowStore(root).save(
                document,
                document.revision,
                run_active=workflow_run_active(app, workflow_id),
            )
            if app.state.triggers is not None:
                app.state.triggers.activate(saved, root)
            return saved.model_dump(mode="json")
        except ValueError as exc:
            return error("REVISION_CONFLICT", str(exc), 409)

    @app.patch("/api/workflows/{workflow_id}")
    async def patch_workflow(workflow_id: str, request: Request) -> Any:
        root = root_for(app, workflow_id)
        current = WorkflowStore(root).load()
        patch = await request.json()
        expected = patch.pop("revision", current.revision)
        merged = merge_patch(current.model_dump(mode="json"), patch)
        document = WorkflowDocument.model_validate(merged)
        try:
            saved = WorkflowStore(root).save(
                document,
                expected,
                run_active=workflow_run_active(app, workflow_id),
            )
            if app.state.triggers is not None:
                app.state.triggers.activate(saved, root)
            return saved.model_dump(mode="json")
        except ValueError as exc:
            return error("REVISION_CONFLICT", str(exc), 409)

    @app.delete("/api/workflows/{workflow_id}")
    def close_workflow(workflow_id: str, purge_cache: bool = False) -> dict[str, bool]:
        root = root_for(app, workflow_id)
        if app.state.triggers is not None:
            app.state.triggers.deactivate(workflow_id)
        app.state.roots.pop(workflow_id)
        if purge_cache:
            CacheManager(root).reset_all()
        return {"closed": True}

    @app.post("/api/workflows/{workflow_id}/duplicate", status_code=201)
    def duplicate_workflow(workflow_id: str, request: CreateRequest) -> Any:
        source = root_for(app, workflow_id)
        target = Path(request.parent_dir) / f"{request.name}.weft"
        if target.exists():
            return error("WORKFLOW_EXISTS", "目录已存在", 409)
        shutil.copytree(
            source, target, ignore=shutil.ignore_patterns(".runs", ".venv", "__pycache__")
        )
        document = WorkflowStore(target).load()
        document.id = f"wf_{secrets.token_hex(6)}"
        document.revision = 1
        (target / "workflow.json").write_text(document.model_dump_json(indent=2), encoding="utf-8")
        app.state.roots[document.id] = target
        return {"id": document.id, "path": str(target), "revision": 1}

    @app.get("/api/workflows/{workflow_id}/pack/preflight")
    def pack_preflight(workflow_id: str, exclude_data: bool = False) -> dict[str, Any]:
        from weft.workflow.packaging import preflight

        root = root_for(app, workflow_id)
        return preflight(root, app.state.registry, exclude_data).as_dict()

    @app.post("/api/workflows/{workflow_id}/pack")
    def pack(workflow_id: str, request: PackRequest) -> Any:
        from weft.workflow.packaging import PackError, pack_workflow

        try:
            path = pack_workflow(
                root_for(app, workflow_id),
                Path(request.output) if request.output else None,
                request.exclude_data,
                request.confirm_warnings,
                app.state.registry,
            )
        except PackError as exception:
            return JSONResponse(
                status_code=400 if exception.report.errors else 409,
                content={
                    "error": {
                        "code": "PACK_PREFLIGHT_FAILED",
                        "message": str(exception),
                        "detail": exception.report.as_dict(),
                    }
                },
            )
        job_id = f"pack_{secrets.token_hex(6)}"
        return {"job_id": job_id, "path": str(path)}

    @app.post("/api/workflows/unpack")
    async def unpack(request: UnpackRequest) -> Any:
        from weft.worker.environment import EnvironmentError as WorkflowEnvironmentError
        from weft.workflow.packaging import UnpackError, unpack_workflow

        try:
            root = await asyncio.to_thread(
                unpack_workflow, Path(request.zip_path), Path(request.dest_dir)
            )
            document = WorkflowStore(root).load()
        except (OSError, ValueError, UnpackError, WorkflowEnvironmentError) as exception:
            return error("UNPACK_FAILED", str(exception), 400)
        app.state.roots[document.id] = root
        if app.state.triggers is not None:
            app.state.triggers.activate(document, root)
        return {"id": document.id, "path": str(root)}

    @app.get("/api/workflows/{workflow_id}/env")
    def environment(workflow_id: str) -> dict[str, Any]:
        env = WorkflowEnvironment(root_for(app, workflow_id))
        return {
            "status": "ok" if env.python.exists() else "missing",
            "python": str(env.python),
            "uv_output": "",
        }

    @app.post("/api/workflows/{workflow_id}/env/sync")
    def sync_environment(workflow_id: str) -> dict[str, str]:
        WorkflowEnvironment(root_for(app, workflow_id)).sync()
        return {"status": "ok"}

    @app.post("/api/workflows/{workflow_id}/nodes/{node_id}/column-hints")
    def column_hints(workflow_id: str, node_id: str) -> dict[str, list[str]]:
        root = root_for(app, workflow_id)
        document = WorkflowStore(root).load()
        result: dict[str, list[str]] = {}
        for edge in document.edges:
            if edge.target != node_id:
                continue
            for path in sorted(root.glob(".runs/r_*/meta.json"), reverse=True):
                meta = json.loads(path.read_text(encoding="utf-8"))
                source = meta["nodes"].get(edge.source)
                if not source:
                    continue
                reference = source["outputs"].get(edge.sourcePort)
                if not reference or reference["kind"] != "table":
                    continue
                table_path = Path(reference["path"])
                if not table_path.is_absolute():
                    table_path = root / table_path
                with pa.memory_map(str(table_path)) as stream:
                    schema = pa.ipc.open_file(stream).schema
                result[edge.targetPort] = schema.names
                break
        return result

    @app.get("/api/workflows/{workflow_id}/nodes/{node_id}/status")
    def node_status(workflow_id: str, node_id: str) -> dict[str, Any]:
        root = root_for(app, workflow_id)
        for path in sorted((root / ".runs").glob("r_*/meta.json"), reverse=True):
            meta = json.loads(path.read_text(encoding="utf-8"))
            if node_id in meta["nodes"]:
                node = meta["nodes"][node_id]
                return {
                    "status": node["status"],
                    "from_cache": node["from_cache"],
                    "last_run_id": meta["run_id"],
                }
        return {"status": "configured", "from_cache": False, "last_run_id": None}

    @app.get("/api/workflows/{workflow_id}/validate")
    @app.post("/api/workflows/{workflow_id}/validate")
    def validate(workflow_id: str, document: WorkflowDocument | None = None) -> Any:
        document = document or WorkflowStore(root_for(app, workflow_id)).load()
        report = validate_workflow(document, app.state.registry.declarations_for(document))
        return {
            "errors": [issue.__dict__ for issue in report.errors],
            "warnings": [issue.__dict__ for issue in report.warnings],
        }

    @app.get("/api/nodes/types")
    def node_types() -> list[dict[str, Any]]:
        return [node.manifest({}) for node in app.state.registry.all()]

    @app.get("/api/workflows/{workflow_id}/triggers/status")
    def trigger_health(workflow_id: str) -> Any:
        if app.state.triggers is None:
            return {}
        return app.state.triggers.health.get(workflow_id, {})

    @app.post("/api/workflows/{workflow_id}/trigger")
    async def http_trigger(workflow_id: str, request: Request, wait: bool = False) -> Any:
        from weft.engine.errors import RunQueueFullError
        from weft.triggers.http import HttpTriggerDisabledError

        root = root_for(app, workflow_id)
        try:
            result = await app.state.http.trigger(
                WorkflowStore(root).load(),
                root,
                app.state.registry,
                await request.json(),
                request.headers.get("authorization", "").removeprefix("Bearer "),
                request.client.host if request.client else "unknown",
                wait,
            )
        except HttpTriggerDisabledError:
            return error("NOT_FOUND", "触发器不存在或未启用", 404)
        except PermissionError as exception:
            limited = "Too many" in str(exception)
            return error(
                "RATE_LIMITED" if limited else "UNAUTHORIZED",
                str(exception),
                429 if limited else 401,
            )
        except RunQueueFullError as exception:
            return error("RUN_QUEUE_FULL", str(exception), 409)
        status = 200 if result.get("disposition") == "dropped" else 202
        return JSONResponse(result, status_code=status)

    @app.get("/api/workflows/{workflow_id}/resources/preflight")
    async def resource_preflight(workflow_id: str) -> Any:
        from weft.workflow.resources import preflight_resources

        return await preflight_resources(
            WorkflowStore(root_for(app, workflow_id)).load(),
            root_for(app, workflow_id),
            app.state.registry,
            app.state.engine,
        )

    @app.post("/api/workflows/{workflow_id}/runs", status_code=202)
    async def run(workflow_id: str, request: RunRequest, http_request: Request) -> Any:
        from weft.workflow.resources import preflight_resources

        root = root_for(app, workflow_id)
        store = WorkflowStore(root)
        document = store.load()
        report = await preflight_resources(
            document, root, app.state.registry, app.state.engine, request.overrides
        )
        if report["missing"] and not request.allow_missing_resources:
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "MISSING_EXTERNAL_RESOURCES",
                        "message": "外部资源缺失",
                        "detail": report,
                    }
                },
            )
        result = await app.state.coordinator.submit(
            document,
            root,
            app.state.registry,
            trigger={
                "source": "manual",
                "ts": datetime.now(UTC).isoformat(),
                "payload": {"overrides": request.overrides},
            },
            scope=request.scope,
            trace_id=http_request.state.trace_id,
        )
        return {"run_id": result.run_id, "disposition": result.disposition}

    @app.post("/api/workflows/{workflow_id}/chat", status_code=202)
    async def chat(workflow_id: str, request: ChatRequest) -> Any:
        from weft.triggers.chat import ChatDisabledError

        root = root_for(app, workflow_id)
        try:
            result = await app.state.chat.send(
                WorkflowStore(root).load(),
                root,
                app.state.registry,
                request.message,
                request.session_id,
            )
        except ChatDisabledError as exception:
            return error("CHAT_DISABLED", str(exception), 400)
        except ValueError as exception:
            return error("INVALID_CHAT_MESSAGE", str(exception), 400)
        return JSONResponse(result, status_code=200 if result["disposition"] == "dropped" else 202)

    @app.get("/api/workflows/{workflow_id}/chat/{session_id}")
    def chat_history(workflow_id: str, session_id: str) -> Any:
        from weft.triggers.chat import ChatSessionStore

        return ChatSessionStore(root_for(app, workflow_id)).history(session_id)

    @app.post("/api/workflows/{workflow_id}/chat/{session_id}/clear")
    def clear_chat(workflow_id: str, session_id: str, request: ChatClearRequest) -> Any:
        from weft.triggers.chat import ChatSessionStore

        ChatSessionStore(root_for(app, workflow_id)).clear(session_id, request.clear_memory)
        return {"cleared": True}

    @app.get("/api/workflows/{workflow_id}/runs")
    def runs(workflow_id: str, limit: int = 20) -> list[dict[str, Any]]:
        from weft.workflow.history import RunHistory

        return RunHistory(root_for(app, workflow_id)).list_runs(limit)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> Any:
        if run_id in app.state.engine.runs:
            return dict(app.state.engine.runs[run_id].record.to_dict())
        from weft.workflow.history import RunHistory

        for root in app.state.roots.values():
            try:
                return RunHistory(root).get(run_id)
            except (ValueError, FileNotFoundError):
                continue
        return error("RUN_NOT_FOUND", "运行记录不存在", 404)

    @app.post("/api/runs/{run_id}/cancel", status_code=202)
    def cancel(run_id: str) -> dict[str, Any]:
        app.state.engine.cancel(run_id)
        return {"cancelled": True}

    @app.post("/api/runs/{run_id}/confirm")
    def confirm(run_id: str, request: ConfirmRequest) -> Any:
        if request.decision not in {"approve", "reject"}:
            return error("INVALID_CONFIRMATION", "decision 必须为 approve 或 reject", 400)
        resolved = app.state.confirmations.resolve(
            request.request_id, request.decision, request.modified_args
        )
        if not resolved:
            return error("CONFIRMATION_NOT_FOUND", "确认请求不存在或已结束", 404)
        return {"resolved": True}

    @app.get("/api/runs/{run_id}/log")
    def logs(run_id: str) -> list[dict[str, Any]]:
        path = run_root(app, run_id) / "log.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    @app.get("/api/runs/{run_id}/audit")
    def audit(run_id: str) -> list[dict[str, Any]]:
        path = run_root(app, run_id) / "audit.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    @app.get("/api/runs/{run_id}/nodes/{node_id}/trace")
    def trace(run_id: str, node_id: str) -> list[dict[str, Any]]:
        path = run_root(app, run_id) / "nodes" / f"{node_id}.trace.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    @app.get("/api/runs/{run_id}/changes")
    def changes(run_id: str) -> Any:
        from weft.sandbox.review import ChangeReviewStore

        try:
            return ChangeReviewStore(workflow_root_for_run(app, run_id), run_id).load().to_dict()
        except FileNotFoundError:
            return error("CHANGES_NOT_READY", "变更尚未生成", 404)

    @app.get("/api/runs/{run_id}/changes/diff")
    def change_diff(run_id: str, path: str) -> Any:
        from weft.sandbox.review import ChangeReviewStore

        return ChangeReviewStore(workflow_root_for_run(app, run_id), run_id).diff(Path(path))

    @app.post("/api/runs/{run_id}/changes/apply")
    def apply_changes(run_id: str, request: ChangeApplyRequest) -> Any:
        from weft.sandbox.review import ChangeReviewStore, ProtectedChangeError

        try:
            results = ChangeReviewStore(workflow_root_for_run(app, run_id), run_id).apply(
                [Path(path) for path in request.paths], request.overwrite_conflicts
            )
        except ProtectedChangeError as exception:
            return error("PROTECTED_CHANGE", str(exception), 400)
        return {"results": [change.to_dict() for change in results]}

    @app.post("/api/runs/{run_id}/changes/discard")
    def discard_changes(run_id: str, request: ChangeDiscardRequest) -> Any:
        from weft.sandbox.review import ChangeReviewStore

        results = ChangeReviewStore(workflow_root_for_run(app, run_id), run_id).discard(
            [Path(path) for path in request.paths] if request.paths is not None else None
        )
        return {"results": [change.to_dict() for change in results]}

    @app.post("/api/workflows/{workflow_id}/reset")
    def reset(workflow_id: str) -> dict[str, bool]:
        CacheManager(root_for(app, workflow_id)).reset_all()
        return {"reset": True}

    @app.post("/api/workflows/{workflow_id}/nodes/{node_id}/reset")
    def reset_node(workflow_id: str, node_id: str) -> dict[str, bool]:
        CacheManager(root_for(app, workflow_id)).reset(node_id)
        return {"reset": True}

    @app.get("/api/runs/{run_id}/audit")
    def run_audit(run_id: str) -> list[dict[str, Any]]:
        path = run_root(app, run_id) / "audit.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    @app.get("/api/workflows/{workflow_id}/nodes/{node_id}/ports/{port}")
    def current_port_view(
        workflow_id: str,
        node_id: str,
        port_name: str = RoutePath(alias="port"),
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "",
        desc: bool = False,
    ) -> Any:
        root = root_for(app, workflow_id)
        for path in sorted(root.glob(".runs/r_*/meta.json"), reverse=True):
            meta = json.loads(path.read_text(encoding="utf-8"))
            reference = meta["nodes"].get(node_id, {}).get("outputs", {}).get(port_name)
            if reference:
                return port_response(reference, root, offset, limit, sort_by, desc)
        return error("PORT_NOT_EXECUTED", "节点未执行", 404)

    @app.get("/api/runs/{run_id}/nodes/{node_id}/ports/{port}")
    def port_view(
        run_id: str,
        node_id: str,
        port_name: str = RoutePath(alias="port"),
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "",
        desc: bool = False,
    ) -> Any:
        root = workflow_root_for_run(app, run_id)
        if run_id in app.state.engine.runs:
            record = app.state.engine.runs[run_id].record.nodes.get(node_id)
            outputs = record.outputs if record is not None else {}
            value = outputs[port_name].model_dump(mode="json") if port_name in outputs else None
        else:
            from weft.workflow.history import RunHistory

            node = RunHistory(root).get(run_id)["nodes"].get(node_id, {})
            value = node.get("outputs", {}).get(port_name)
        if value is None:
            return error("PORT_NOT_EXECUTED", "节点未执行", 404)
        return port_response(value, root, offset, limit, sort_by, desc)

    @app.websocket("/api/ws")
    async def websocket(socket: WebSocket) -> None:
        await socket.accept()
        try:
            message = await socket.receive_json()
        except WebSocketDisconnect:
            return
        if message.get("op") != "authenticate" or not secrets.compare_digest(
            message.get("token", ""), session.token
        ):
            await socket.send_json({"error": {"code": "UNAUTHORIZED", "message": "认证失败"}})
            await socket.close(code=1008)
            return
        topics: set[str] = set()
        queue, _ = app.state.bus.subscribe(lambda event: f"run:{event['run_id']}" in topics)
        sender = asyncio.create_task(send_events(socket, queue))
        try:
            while True:
                command = await socket.receive_json()
                if command.get("op") == "subscribe":
                    topics.update(command.get("topics", []))
                    await socket.send_json(
                        {
                            "topic": "system",
                            "event": "subscribed",
                            "data": {"topics": sorted(topics)},
                        }
                    )
                elif command.get("op") == "unsubscribe":
                    topics.difference_update(command.get("topics", []))
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            app.state.bus.unsubscribe(queue)

    packaged_static = Path(__file__).resolve().parent.parent / "static"
    frontend_dist = (
        packaged_static
        if (packaged_static / "index.html").is_file()
        else Path(__file__).resolve().parents[5] / "frontend" / "dist"
    )
    if (frontend_dist / "index.html").is_file():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        if (frontend_dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> Any:
            if path.startswith("api"):
                return error("NOT_FOUND", "接口不存在", 404)
            if path in {"weft-mark.svg", "weft-logo.svg"}:
                return FileResponse(frontend_dist / path)
            return FileResponse(frontend_dist / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def frontend_missing() -> Any:
            return error("FRONTEND_NOT_BUILT", "请先运行 pnpm -C frontend build", 503)

    return app


def port_response(
    value: dict[str, Any],
    root: Path,
    offset: int,
    limit: int,
    sort_by: str,
    desc: bool,
) -> Any:
    if value["kind"] != "table":
        return value.get("inline")
    path = Path(value["path"])
    if not path.is_absolute():
        path = root / path
    with pa.memory_map(str(path)) as source:
        table = pa.ipc.open_file(source).read_all()
    if sort_by:
        frame = pl.from_arrow(table)
        if not isinstance(frame, pl.DataFrame):
            raise TypeError("Table preview requires a DataFrame")
        table = frame.sort(sort_by, descending=desc, maintain_order=True).to_arrow()
    table = table.slice(offset, limit)
    buffer = io.BytesIO()
    with pa.ipc.new_stream(buffer, table.schema) as writer:
        writer.write_table(table)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/vnd.apache.arrow.stream",
        headers={"X-Weft-Total-Rows": str(value["rows"])},
    )


def merge_patch(document: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_patch(result[key], value)
        else:
            result[key] = value
    return result


async def send_events(socket: WebSocket, queue: asyncio.Queue[dict[str, Any]]) -> None:
    try:
        while True:
            event = await queue.get()
            await socket.send_json(
                {
                    "topic": f"run:{event['run_id']}",
                    "event": event["event"],
                    "ts": event["ts"],
                    "data": {
                        **event["data"],
                        "run_id": event["run_id"],
                        "node_id": event["node_id"],
                    },
                }
            )
    except WebSocketDisconnect:
        return


def error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message, "detail": {}}}
    )


def workflow_run_active(app: FastAPI, workflow_id: str) -> bool:
    run_id = app.state.coordinator.active.get(workflow_id)
    if run_id is None:
        return False
    return app.state.engine.runs[run_id].record.status in {"queued", "running", "waiting"}


def root_for(app: FastAPI, workflow_id: str) -> Path:
    root: Path = app.state.roots[workflow_id]
    return root


def run_root(app: FastAPI, run_id: str) -> Path:
    if run_id in app.state.engine.runs:
        root: Path = app.state.engine.runs[run_id].root
        return root / ".runs" / run_id
    from weft.workflow.history import RunHistory

    for root in app.state.roots.values():
        try:
            path = RunHistory(root).path(run_id)
        except ValueError:
            continue
        if path.is_dir():
            return path
    raise FileNotFoundError(run_id)


def workflow_root_for_run(app: FastAPI, run_id: str) -> Path:
    if run_id in app.state.engine.runs:
        root: Path = app.state.engine.runs[run_id].root
        return root
    return run_root(app, run_id).parent.parent
