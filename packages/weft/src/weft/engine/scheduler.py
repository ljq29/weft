from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import shutil
import traceback
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import polars as pl
import pyarrow as pa
from weft_sdk import Node, weft_ctx
from weft_sdk.context import Cancelled

from weft.engine.cache import CacheManager
from weft.engine.cache_key import (
    CacheKeyInput,
    ExternalInput,
    build_cache_key,
    hash_external_input,
    hash_file,
)
from weft.engine.errors import UnconfiguredNodesError
from weft.engine.loops import execute_loop, region
from weft.engine.models import NodeRecord, NodeStatus, PreparedRun, RunRecord, now
from weft.workflow.models import Edge, WorkflowDocument
from weft.workflow.models import Node as WorkflowNode
from weft.workflow.validation import validate_workflow
from weft.workflow.values import ValueRef


def schema_with_variables(schema: dict[str, Any]) -> dict[str, Any]:
    original = dict(schema)
    if isinstance(original.get("properties"), dict):
        original["properties"] = {
            key: schema_with_variables(value) for key, value in original["properties"].items()
        }
    if isinstance(original.get("items"), dict):
        original["items"] = schema_with_variables(original["items"])
    return {
        "anyOf": [
            original,
            {
                "type": "object",
                "properties": {"$var": {"type": "string"}},
                "required": ["$var"],
                "additionalProperties": False,
            },
        ]
    }


class Engine:
    def __init__(self, worker_pool_factory: Any = None, excel_worker: Any = None) -> None:
        self.runs: dict[str, PreparedRun] = {}
        self.worker_pool_factory = worker_pool_factory
        self.worker_pools: dict[str, Any] = {}
        self.excel_worker = excel_worker
        self.event_sink: Any = None

    def close(self) -> None:
        for pool in self.worker_pools.values():
            pool.close()
        self.worker_pools.clear()
        if self.excel_worker is not None:
            self.excel_worker.close()

    def prepare(
        self,
        workflow: WorkflowDocument,
        root: Path,
        registry: Any,
        trigger: dict[str, Any] | None = None,
        scope: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> PreparedRun:
        workflow = workflow.model_copy(deep=True)
        run_id = run_id or self.new_run_id()
        trigger = trigger or {
            "source": "manual",
            "ts": now(),
            "payload": {},
        }
        scope = scope or {"kind": "all", "node_id": None}
        variables = {variable.name: variable.value for variable in workflow.variables}
        variables.update(trigger["payload"].get("overrides", {}))
        self._precheck(workflow, registry, variables)
        record = RunRecord(
            run_id=run_id,
            workflow_id=workflow.id,
            workflow_revision=workflow.revision,
            trigger=trigger,
            scope=scope,
            nodes={node.id: NodeRecord() for node in workflow.nodes},
        )
        prepared = PreparedRun(root, workflow, registry, record)
        self.runs[run_id] = prepared
        run_dir = root / ".runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        frozen = workflow.model_dump(mode="json")
        frozen["node_manifest"] = [
            {"node_id": node.id, **registry.get(node.type).manifest(node.params)}
            for node in workflow.nodes
        ]
        (run_dir / "workflow.json").write_text(
            json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._write_meta(prepared)
        return prepared

    async def run(self, prepared: PreparedRun) -> RunRecord:
        record = prepared.record
        record.status = "running"
        record.started_at = now()
        self._write_meta(prepared)
        self._event(prepared, "run.started", "", {"status": "running"})
        predecessors = self._predecessors(prepared.workflow)
        scope_nodes = self._scope_nodes(prepared.workflow, record.scope)
        remaining = set(record.nodes)
        for loop_start in prepared.workflow.nodes:
            if loop_start.type == "flow.loop_start":
                body, end_id = region(prepared.workflow, loop_start)
                remaining.difference_update(body | {end_id})
        inflight: dict[str, asyncio.Task[None]] = {}
        try:
            while remaining or inflight:
                ready = [
                    node_id
                    for node_id in remaining
                    if all(
                        predecessor not in remaining
                        and predecessor not in inflight
                        and record.nodes[predecessor].status
                        in {
                            "executed",
                            "failed",
                            "cancelled",
                            "out_of_scope",
                            "skipped_branch",
                            "skipped_upstream",
                        }
                        for predecessor in predecessors[node_id]
                    )
                ]
                for node_id in ready:
                    remaining.remove(node_id)
                    if prepared.cancel_event.is_set():
                        self._finish_node(prepared, node_id, "cancelled")
                        continue
                    if node_id not in scope_nodes:
                        self._finish_node(prepared, node_id, "out_of_scope")
                        continue
                    if self._skipped_input(prepared, node_id):
                        self._finish_node(prepared, node_id, "skipped_branch")
                        continue
                    inflight[node_id] = asyncio.create_task(self._execute_node(prepared, node_id))
                if not inflight:
                    continue
                done, _ = await asyncio.wait(inflight.values(), return_when=asyncio.FIRST_COMPLETED)
                completed = [node_id for node_id, task in inflight.items() if task in done]
                for node_id in completed:
                    task = inflight.pop(node_id)
                    task.result()
                if str(record.status) == "failed":
                    for task in inflight.values():
                        task.cancel()
                    if inflight:
                        await asyncio.gather(*inflight.values(), return_exceptions=True)
                    inflight.clear()
                    for node_id in remaining:
                        self._finish_node(prepared, node_id, "skipped_upstream")
                    remaining.clear()
        except asyncio.CancelledError:
            prepared.cancel_event.set()
            for task in inflight.values():
                task.cancel()
            await asyncio.gather(*inflight.values(), return_exceptions=True)
            for node_id in remaining:
                self._finish_node(prepared, node_id, "skipped_upstream")
            record.status = "cancelled"
        if prepared.cancel_event.is_set():
            record.status = "cancelled"
        elif record.status == "running":
            record.status = "succeeded"
        record.finished_at = now()
        pool = self.worker_pools.pop(prepared.record.run_id, None)
        if pool is not None:
            pool.close()
        if self.excel_worker is not None:
            try:
                await self.excel_worker.release_run(prepared.record.run_id)
            except Exception as error:
                record.status = "failed"
                self._event(prepared, "run.warning", "", {"message": str(error)})
        self._event(prepared, "run.finished", "", {"status": record.status, "usage": record.usage})
        self._write_meta(prepared)
        record.finished.set()
        if prepared.on_finished is not None:
            prepared.on_finished(prepared)
        return record

    def cancel(self, run_id: str) -> None:
        self.runs[run_id].cancel_event.set()

    async def _execute_node(self, prepared: PreparedRun, node_id: str) -> None:
        record = prepared.record.nodes[node_id]
        record.status = "running"
        record.started_at = now()
        self._event(prepared, "node.started", node_id)
        node = next(item for item in prepared.workflow.nodes if item.id == node_id)
        declaration = prepared.registry.get(node.type)
        cache = CacheManager(prepared.root)
        cache_key: str | None = None
        inputs: dict[str, Any] = {}
        try:
            inputs, variables = self._inputs(prepared, node_id)
            params = self._resolve_params(node.params, variables)
            if declaration.cache_policy == "pure":
                cache_key = self._cache_key(prepared, node, params)
                cached = cache.load(node_id, cache_key)
                if cached is not None:
                    record.outputs = cache.materialize(
                        prepared.root / ".runs" / prepared.record.run_id, node_id, cached.outputs
                    )
                    record.activated_ports = cached.activated_ports
                    record.from_cache = True
                    record.status = "executed"
                    record.finished_at = now()
                    cache.touch(node_id)
                    self._event(prepared, "node.finished", node_id, {"from_cache": True})
                    return
            if node.type == "flow.trigger":
                event = prepared.record.trigger
                outputs = {
                    "variable": event,
                    "message": [{"role": "user", "content": event["payload"]["message"]}]
                    if event["source"] == "chat"
                    else [],
                }
                activated = None
            else:
                if node.type == "flow.loop_start":
                    await execute_loop(self, prepared, node)
                    result = {}
                elif declaration.lane == "trusted_worker" and self.worker_pool_factory is not None:
                    pool = self.worker_pools.get(prepared.record.run_id)
                    if pool is None:
                        pool = self.worker_pool_factory(prepared.root, prepared.record.run_id)
                        self.worker_pools[prepared.record.run_id] = pool
                    result = await pool.execute(
                        node_id,
                        node.type,
                        params,
                        self._input_refs(prepared, node_id),
                        variables,
                    )
                    if "error" in result:
                        raise RuntimeError(result["error"]["message"])
                    worker_result = result
                    result = dict(worker_result["outputs"])
                    if "activated_ports" in worker_result:
                        result["activated_ports"] = worker_result["activated_ports"]
                else:
                    result = await asyncio.to_thread(
                        self._execute_sync, prepared, declaration, node, inputs, variables, params
                    )
                outputs = dict(result)
                activated_raw = outputs.pop("activated_ports", None)
                activated = (
                    list(activated_raw) if isinstance(activated_raw, (list, tuple)) else None
                )
            output_dir = prepared.root / ".runs" / prepared.record.run_id / "outputs" / node_id
            if prepared.iteration_index is not None:
                output_dir = output_dir / f"iteration-{prepared.iteration_index}"
            for port, value in outputs.items():
                reference: ValueRef
                if isinstance(value, ValueRef):
                    reference = value
                    if reference.path is not None and reference.path.is_absolute():
                        output_dir.mkdir(parents=True, exist_ok=True)
                        destination = output_dir / f"{port}{reference.path.suffix}"
                        shutil.copyfile(reference.path, destination)
                        reference = reference.model_copy(
                            update={"path": destination.relative_to(prepared.root)}
                        )
                elif isinstance(value, dict) and value.get("kind") in {"table", "json", "none"}:
                    reference = ValueRef.model_validate(value)
                    if reference.path is not None and reference.path.is_absolute():
                        output_dir.mkdir(parents=True, exist_ok=True)
                        destination = output_dir / f"{port}{reference.path.suffix}"
                        shutil.copyfile(reference.path, destination)
                        reference = reference.model_copy(
                            update={"path": destination.relative_to(prepared.root)}
                        )
                elif isinstance(value, pl.DataFrame):
                    output_dir.mkdir(parents=True, exist_ok=True)
                    path = output_dir / f"{port}.arrow"
                    arrow = value.to_arrow()
                    with path.open("wb") as stream:
                        with pa.ipc.new_file(stream, arrow.schema) as writer:
                            writer.write_table(arrow)
                    reference = ValueRef(
                        kind="table",
                        path=path.relative_to(prepared.root),
                        hash=hash_file(path),
                        rows=value.height,
                        cols=value.width,
                    )
                else:
                    reference = ValueRef.from_json(value, output_dir)
                    if reference.path is not None:
                        reference = reference.model_copy(
                            update={"path": reference.path.relative_to(prepared.root)}
                        )
                record.outputs[port] = reference
            record.activated_ports = activated
            record.status = "executed"
            record.finished_at = now()
            if cache_key is not None:
                cache.store(node_id, cache_key, record.outputs, activated)
            self._event(prepared, "node.finished", node_id)
        except (Cancelled, asyncio.CancelledError):
            record.status = "cancelled"
            record.finished_at = now()
            prepared.record.status = "cancelled"
            self._event(prepared, "node.failed", node_id)
            raise asyncio.CancelledError from None
        except Exception as error:
            record.status = "failed"
            record.finished_at = now()
            record.error = {
                "code": "NODE_EXECUTION_FAILED",
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
                "input_snapshot": {
                    port: value.head(20).to_dicts()
                    if isinstance(value, pl.DataFrame)
                    else repr(value)
                    for port, value in inputs.items()
                },
            }
            prepared.record.status = "failed"
            self._event(prepared, "node.failed", node_id, {"message": str(error)})

    def _cache_key(self, prepared: PreparedRun, node: WorkflowNode, params: dict[str, Any]) -> str:
        declaration = prepared.registry.get(node.type)
        implementation = hashlib.sha256(
            inspect.getsource(declaration.__class__).encode("utf-8")
        ).hexdigest()
        input_hashes = []
        for raw_edge in prepared.workflow.edges:
            edge = Edge.model_validate(raw_edge)
            if edge.target != node.id:
                continue
            value = prepared.record.nodes[edge.source].outputs.get(edge.sourcePort)
            if value is not None and value.hash is not None:
                input_hashes.append((edge.targetPort, value.hash))
        external_hashes = []
        for external in declaration.cache_inputs:
            value = params.get(external.name)
            if not isinstance(value, str):
                raise ValueError(f"Cache input '{external.name}' must be a path")
            external_hashes.append(
                (
                    external.name,
                    hash_external_input(
                        ExternalInput(
                            external.name,
                            external.kind,
                            prepared.root / value,
                            params.get("pattern", "*"),
                            params.get("recursive", False),
                        )
                    ),
                )
            )
        user_code_hash = ""
        if node.type == "code.python" and params.get("source") == "file":
            user_code_hash = hash_file(prepared.root / params["path"])
        lock = prepared.root / "uv.lock"
        return build_cache_key(
            CacheKeyInput(
                node.type,
                node.node_version,
                f"sha256:{implementation}",
                params,
                tuple(input_hashes),
                tuple(external_hashes),
                user_code_hash,
                hash_file(lock) if lock.exists() else "",
                prepared.iteration_index,
            )
        )

    def _execute_sync(
        self,
        prepared: PreparedRun,
        declaration: Node,
        node: WorkflowNode,
        inputs: dict[str, Any],
        variables: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        from weft.nodes.excel import ExcelClient

        with weft_ctx.activate(
            root=prepared.root,
            run_id=prepared.record.run_id,
            variables=variables,
            log=lambda level, message: self._event(
                prepared, "node.log", node.id, {"level": level, "message": message}
            ),
            progress=lambda fraction, message: self._event(
                prepared,
                "node.progress",
                node.id,
                {"fraction": fraction, "message": message},
            ),
            cancelled=prepared.cancel_event.is_set,
            excel=ExcelClient(self.excel_worker) if self.excel_worker is not None else None,
        ):
            return declaration.execute(weft_ctx, inputs, params)

    def _input_refs(self, prepared: PreparedRun, node_id: str) -> dict[str, Any]:
        result = {}
        for raw_edge in prepared.workflow.edges:
            edge = Edge.model_validate(raw_edge)
            if edge.target != node_id:
                continue
            value = prepared.record.nodes[edge.source].outputs.get(edge.sourcePort)
            if value is not None:
                result[edge.targetPort] = value.model_dump(mode="json")
        return result

    def _inputs(self, prepared: PreparedRun, node_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        inputs: dict[str, Any] = {}
        variables = {variable.name: variable.value for variable in prepared.workflow.variables}
        variables.update(prepared.record.trigger["payload"].get("overrides", {}))
        edges = sorted(
            (
                Edge.model_validate(edge)
                for edge in prepared.workflow.edges
                if edge.target == node_id
            ),
            key=lambda edge: edge.order,
        )
        for edge in edges:
            value = prepared.record.nodes[edge.source].outputs.get(edge.sourcePort)
            if value is None:
                continue
            content = self._read_value(prepared, value)
            if value.kind == "json" and edge.targetPort == "variables":
                variables.update(content)
            inputs[edge.targetPort] = content
        return inputs, variables

    def _read_value(self, prepared: PreparedRun, value: ValueRef) -> Any:
        if value.inline is not None:
            return value.inline
        if value.path is None:
            return None
        path = value.path if value.path.is_absolute() else prepared.root / value.path
        if value.kind == "table":
            with pa.memory_map(str(path)) as source:
                return pl.from_arrow(pa.ipc.open_file(source).read_all())
        return json.loads(path.read_text(encoding="utf-8"))

    def _resolve_params(self, value: Any, variables: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            if set(value) == {"$var"}:
                name = value["$var"]
                if name not in variables:
                    raise ValueError(f"Flow variable '{name}' not found")
                return variables[name]
            return {key: self._resolve_params(item, variables) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve_params(item, variables) for item in value]
        return value

    def _skipped_input(self, prepared: PreparedRun, node_id: str) -> bool:
        incoming = [
            Edge.model_validate(edge) for edge in prepared.workflow.edges if edge.target == node_id
        ]
        skipped = []
        successful = []
        for edge in incoming:
            source = prepared.record.nodes[edge.source]
            activated = source.activated_ports
            is_skipped = source.status in {"skipped_branch", "skipped_upstream"} or (
                activated is not None and edge.sourcePort not in activated
            )
            skipped.append(is_skipped)
            successful.append(not is_skipped and source.status == "executed")
        declaration = prepared.registry.get(
            next(node.type for node in prepared.workflow.nodes if node.id == node_id)
        )
        if declaration.type == "flow.merge":
            return not any(successful)
        return any(skipped)

    def _precheck(
        self, workflow: WorkflowDocument, registry: Any, variables: dict[str, Any]
    ) -> None:
        errors = [
            {"node_id": issue.node_id, "message": issue.message}
            for issue in validate_workflow(workflow, registry.declarations_for(workflow)).errors
        ]
        for node in workflow.nodes:
            try:
                declaration = registry.get(node.type)
                jsonschema.validate(node.params, schema_with_variables(declaration.params_schema))
            except Exception as error:
                errors.append({"node_id": node.id, "message": str(error)})
        if errors:
            raise UnconfiguredNodesError(str(errors))

    def _predecessors(self, workflow: WorkflowDocument) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {node.id: set() for node in workflow.nodes}
        for raw_edge in workflow.edges:
            edge = Edge.model_validate(raw_edge)
            result[edge.target].add(edge.source)
        return result

    def _scope_nodes(self, workflow: WorkflowDocument, scope: dict[str, Any]) -> set[str]:
        all_nodes = {node.id for node in workflow.nodes}
        if scope["kind"] == "all":
            return all_nodes
        target = scope["node_id"]
        predecessors = self._predecessors(workflow)
        successors: dict[str, set[str]] = defaultdict(set)
        for source, targets in predecessors.items():
            for item in targets:
                successors[item].add(source)

        def walk(start: str, links: dict[str, set[str]]) -> set[str]:
            seen = {start}
            pending = [start]
            while pending:
                current = pending.pop()
                for item in links[current]:
                    if item not in seen:
                        seen.add(item)
                        pending.append(item)
            return seen

        if scope["kind"] == "to_node":
            return walk(target, predecessors)
        if scope["kind"] == "from_node":
            return walk(target, successors)
        return {target}

    def _finish_node(self, prepared: PreparedRun, node_id: str, status: NodeStatus) -> None:
        record = prepared.record.nodes[node_id]
        record.status = status
        record.finished_at = now()
        self._event(prepared, "node.status", node_id, {"status": status})

    def _event(
        self, prepared: PreparedRun, event: str, node_id: str, data: dict[str, Any] | None = None
    ) -> None:
        line = {
            "event": event,
            "run_id": prepared.record.run_id,
            "node_id": node_id,
            "ts": now(),
            "data": data or {},
        }
        if self.event_sink is not None:
            self.event_sink(line)
        path = prepared.root / ".runs" / prepared.record.run_id / "log.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(line, ensure_ascii=False) + "\n")

    def _write_meta(self, prepared: PreparedRun) -> None:
        path = prepared.root / ".runs" / prepared.record.run_id / "meta.json"
        path.write_text(
            json.dumps(prepared.record.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def new_run_id() -> str:
        return datetime.now(UTC).strftime("r_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
