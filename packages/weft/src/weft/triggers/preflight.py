from __future__ import annotations

from typing import Any


async def precheck_excel_targets(workflow: Any, engine: Any) -> None:
    targets = [
        node.params.get("target", {})
        for node in workflow.nodes
        if node.type == "excel.connect" and node.params.get("mode") == "attach_visible"
    ]
    if not targets:
        return
    if engine.excel_worker is None:
        raise ValueError("Excel target precheck requires ExcelWorker")
    instances = await engine.excel_worker.submit("list_instances")
    for target in targets:
        workbook = target.get("workbook")
        path = target.get("path")
        if not workbook and not path:
            raise ValueError("Unattended Excel target requires a stable workbook or path")
        matches = [
            instance
            for instance in instances
            if (not workbook or workbook in instance.get("workbooks", []))
            and (
                not path
                or any(str(item).lower() == str(path).lower() for item in instance.get("paths", []))
            )
        ]
        if len(matches) != 1:
            raise ValueError(f"Excel target cannot be resolved uniquely; matches={len(matches)}")
