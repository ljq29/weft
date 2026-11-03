from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from weft.agent.settings import SettingsStore


def _nodes(workflow: Any) -> list[Any]:
    from types import SimpleNamespace

    result = []
    for node in workflow.nodes:
        result.append(node)
        if node.type == "flow.metanode":
            graph = node.params.get("graph", {})
            nested = [SimpleNamespace(**item) for item in graph.get("nodes", [])]
            result.extend(_nodes(SimpleNamespace(nodes=nested)))
    return result


def _value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict) and set(value) == {"$var"}:
        return variables.get(value["$var"])
    return value


async def preflight_resources(
    workflow: Any,
    root: Path,
    registry: Any,
    engine: Any = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    variables = {variable.name: variable.value for variable in workflow.variables}
    variables.update(overrides or {})
    resources: list[dict[str, Any]] = []
    excel_instances: list[dict[str, Any]] | None = None
    for node in _nodes(workflow):
        try:
            declaration = registry.get(node.type)
        except KeyError:
            continue
        declared = [*declaration.external_resources, *declaration.cache_inputs]
        for resource in declared:
            param = getattr(resource, "param", None) or resource.name
            value = _value(node.params.get(param), variables)
            if value is None or value == "":
                continue
            kind = resource.kind
            item = {
                "node_id": node.id,
                "param": param,
                "kind": kind,
                "value": str(value),
                "status": "ok",
                "message": "",
            }
            if kind in {"file", "directory"}:
                path = Path(str(value))
                path = path if path.is_absolute() else root / path
                valid = path.is_file() if kind == "file" else path.is_dir()
                if not valid:
                    item.update(status="missing", message=f"路径不存在或类型不符：{path}")
            elif kind == "llm":
                if str(value) not in SettingsStore().read().get("llm", {}):
                    item.update(status="missing", message=f"LLM 配置不存在：{value}")
            elif kind in {"executable", "pi"}:
                path = Path(str(value))
                exists = path.is_file() if path.is_absolute() else shutil.which(str(value))
                if not exists:
                    item.update(status="missing", message=f"可执行文件不存在：{value}")
            elif kind == "workbook":
                if node.params.get("mode") != "open_existing":
                    continue
                if engine is None or engine.excel_worker is None:
                    item.update(status="missing", message="ExcelWorker 未配置")
                else:
                    if excel_instances is None:
                        excel_instances = await engine.excel_worker.submit("list_instances")
                    opened = {
                        name
                        for instance in excel_instances
                        for name in instance.get("workbooks", [])
                    }
                    if str(value) not in opened:
                        item.update(status="missing", message=f"工作簿未打开：{value}")
            resources.append(item)
    missing = [item for item in resources if item["status"] != "ok"]
    return {"ok": not missing, "resources": resources, "missing": missing}
