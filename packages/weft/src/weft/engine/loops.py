from __future__ import annotations

from typing import Any

import polars as pl
import pyarrow as pa

from weft.engine.cache_key import hash_file
from weft.engine.models import NodeRecord, now
from weft.workflow.models import Edge, Node
from weft.workflow.values import ValueRef


def region(workflow: Any, start: Node) -> tuple[set[str], str]:
    end = next(
        node.id
        for node in workflow.nodes
        if node.type == "flow.loop_end"
        and node.params.get("loop_id") == start.params.get("loop_id")
    )
    successors: dict[str, set[str]] = {node.id: set() for node in workflow.nodes}
    for raw in workflow.edges:
        edge = Edge.model_validate(raw)
        successors[edge.source].add(edge.target)
    body: set[str] = set()
    pending = list(successors[start.id])
    while pending:
        current = pending.pop()
        if current == end:
            continue
        if current not in body:
            body.add(current)
            pending.extend(successors[current])
    return body, end


def set_outputs(prepared: Any, node_id: str, outputs: dict[str, Any]) -> None:
    record = prepared.record.nodes[node_id]
    output_dir = prepared.root / ".runs" / prepared.record.run_id / "outputs" / node_id
    for port, value in outputs.items():
        if isinstance(value, pl.DataFrame):
            output_dir.mkdir(parents=True, exist_ok=True)
            suffix = "" if prepared.iteration_index is None else f"-{prepared.iteration_index}"
            path = output_dir / f"{port}{suffix}.arrow"
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


def iterations(
    prepared: Any, node: Node, inputs: dict[str, Any]
) -> list[tuple[pl.DataFrame | None, dict[str, Any]]]:
    params = node.params
    mode = params["mode"]
    table = inputs.get("in")
    if mode == "row":
        if not isinstance(table, pl.DataFrame):
            raise TypeError("Row loop requires a Table input")
        return [
            (table.slice(index, 1), row) for index, row in enumerate(table.iter_rows(named=True))
        ]
    if mode == "chunk":
        if not isinstance(table, pl.DataFrame):
            raise TypeError("Chunk loop requires a Table input")
        size = params.get("chunk_size", 100)
        return [
            (table.slice(index, size), {"chunk_index": index // size})
            for index in range(0, table.height, size)
        ]
    step = params.get("step", 1)
    if step == 0:
        raise ValueError("step 不能为 0")
    start = params.get("from", 0)
    end = params["to"]
    return [(None, {"i": index}) for index in range(start, end, step)]


async def execute_loop(engine: Any, prepared: Any, start: Node) -> None:
    body, end_id = region(prepared.workflow, start)
    inputs, _ = engine._inputs(prepared, start.id)
    values = iterations(prepared, start, inputs)
    collected: list[pl.DataFrame] = []
    errors: list[dict[str, Any]] = []
    end = next(node for node in prepared.workflow.nodes if node.id == end_id)
    for index, (table, variables) in enumerate(values):
        prepared.iteration_index = index
        engine._event(
            prepared,
            "node.iteration",
            start.id,
            {"index": index + 1, "total": len(values), "loop_node_id": start.id},
        )
        start_record = prepared.record.nodes[start.id]
        start_record.outputs = {}
        set_outputs(prepared, start.id, {"variables": variables})
        if table is not None:
            set_outputs(prepared, start.id, {"table": table})
        for node_id in body:
            prepared.record.nodes[node_id] = NodeRecord()
        pending = set(body)
        while pending:
            progressed = False
            for node_id in list(pending):
                predecessors = engine._predecessors(prepared.workflow)[node_id]
                if any(item in pending for item in predecessors):
                    continue
                pending.remove(node_id)
                await engine._execute_node(prepared, node_id)
                progressed = True
                if prepared.record.status == "failed":
                    break
            if not progressed:
                raise ValueError("循环体存在未解析依赖")
            if prepared.record.status == "failed":
                break
        if prepared.record.status == "failed":
            if end.params.get("on_error", "fail") == "skip":
                errors.append({"iteration": index, "error": "failed"})
                prepared.record.status = "running"
                continue
            raise RuntimeError(f"循环在第 {index + 1} 次迭代失败")
        end_inputs, _ = engine._inputs(prepared, end_id)
        result = end_inputs.get("in")
        if isinstance(result, pl.DataFrame):
            collected.append(result)
        elif end.params["mode"] == "variables":
            variables_output = end_inputs.get("variables", {})
            collected.append(pl.DataFrame([variables_output]))
    if errors:
        collected.append(pl.DataFrame([{"_error": str(item["error"])} for item in errors]))
    mode = end.params["mode"]
    if mode == "concat":
        output = pl.concat(collected, how="diagonal") if collected else pl.DataFrame()
    elif mode == "last":
        output = collected[-1] if collected else pl.DataFrame()
    else:
        output = pl.concat(collected, how="diagonal") if collected else pl.DataFrame()
    set_outputs(prepared, end_id, {"out": output})
    end_record = prepared.record.nodes[end_id]
    end_record.status = "executed"
    end_record.started_at = end_record.started_at or now()
    end_record.finished_at = now()
    prepared.iteration_index = None
