from __future__ import annotations

import asyncio
from typing import Any

import polars as pl
from weft_sdk import CachePolicy, ExternalResource, Lane, Node, Port, ToolCapability


class ExcelClient:
    def __init__(self, worker: Any) -> None:
        self.worker = worker

    def call(self, run_id: str, method: str, *args: Any, **kwargs: Any) -> Any:
        return asyncio.run(self.worker.submit(method, *args, run_id=run_id, **kwargs))


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


def workbook_input(inputs: dict[str, Any], ctx: Any) -> dict[str, Any]:
    workbook: dict[str, Any] = inputs["workbook"]
    if not ctx.excel.call(ctx.run_id, "resolve", workbook):
        raise ValueError("Excel 工作簿引用已失效，请重跑连接上游")
    return workbook


class ExcelConnectNode(Node):
    type = "excel.connect"
    category = "excel"
    name = "Excel Connect"
    display_name = "连接 Excel"
    description = "连接可见 Excel 或创建独立的可见/隐藏实例"
    lane = Lane.TRUSTED_SERVICE
    outputs = (Port("app", "excel", "Excel App 引用"),)
    params_schema = schema(
        {
            "mode": {
                "type": "string",
                "enum": ["attach_visible", "new_visible", "new_hidden"],
                "description": "连接模式",
            },
            "target": {
                "type": "object",
                "description": "稳定工作簿/路径及显式 PID 选择提示",
                "properties": {
                    "workbook": {"type": "string", "description": "工作簿名"},
                    "path": {"type": "string", "description": "工作簿完整路径"},
                    "pid": {"type": "integer", "description": "显式实例 PID"},
                    "window_title": {"type": "string", "description": "窗口标题提示"},
                },
            },
            "on_finish": {
                "type": "string",
                "enum": ["save", "discard"],
                "description": "隐藏实例结束时的显式保存或放弃选择",
            },
        },
        ["mode"],
    )
    portable_params = ["target.path"]

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        mode = params["mode"]
        if mode == "new_hidden" and params.get("on_finish") not in {"save", "discard"}:
            raise ValueError("new_hidden 必须显式选择 on_finish: save 或 discard")
        app = ctx.excel.call(ctx.run_id, "connect", mode, params.get("target"))
        if mode == "new_hidden":
            ctx.excel.call(ctx.run_id, "set_run_finish", params["on_finish"])
        return {"app": app}


class ExcelWorkbookNode(Node):
    type = "excel.workbook"
    category = "excel"
    name = "Excel Workbook"
    display_name = "Excel 工作簿"
    description = "引用已打开工作簿、打开文件或新建工作簿"
    lane = Lane.TRUSTED_SERVICE
    inputs = (Port("app", "excel", "Excel App 引用"),)
    outputs = (Port("workbook", "excel", "Excel Workbook 引用"),)
    params_schema = schema(
        {
            "mode": {
                "type": "string",
                "enum": ["open_existing", "open_file", "new"],
                "description": "工作簿获取方式",
            },
            "name": {"type": "string", "description": "已打开工作簿名"},
            "path": {"type": "string", "description": "相对 Root 的工作簿文件路径"},
        },
        ["mode"],
    )
    portable_params = ["path"]
    external_resources = [
        ExternalResource("name", "workbook"),
        ExternalResource("path", "file"),
    ]

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        target = params.get("name") if params["mode"] == "open_existing" else params.get("path")
        if params["mode"] == "open_file" and target:
            target = str(ctx.resolve(target))
        workbook = ctx.excel.call(ctx.run_id, "workbook", inputs["app"], params["mode"], target)
        return {"workbook": workbook}


class ExcelReadRangeNode(Node):
    type = "excel.read_range"
    category = "excel"
    name = "Excel Read Range"
    display_name = "读取 Excel 区域"
    description = "实时读取 Excel 区域、表对象或命名区域为表格"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.VOLATILE
    tool_capability = ToolCapability.READ_ONLY
    tool_exposed_params = ["sheet", "range", "header"]
    inputs = (Port("workbook", "excel", "Excel Workbook 引用"),)
    outputs = (Port("table", "table", "读取表格"),)
    params_schema = schema(
        {
            "sheet": {"type": "string", "description": "工作表名"},
            "range": {"type": "string", "description": "A1 区域、表对象或命名区域；空为 UsedRange"},
            "header": {"type": "boolean", "description": "首行为表头"},
            "dtype_hints": {
                "type": "object",
                "description": "按列指定 Arrow 类型",
                "additionalProperties": {
                    "type": "string",
                    "description": "Arrow 类型别名，例如 int64、string",
                },
            },
        },
        ["sheet"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        workbook = workbook_input(inputs, ctx)
        table = ctx.excel.call(
            ctx.run_id,
            "read_range",
            workbook,
            params["sheet"],
            params.get("range", ""),
            params.get("header", True),
            params.get("dtype_hints", {}),
        )
        return {"table": pl.DataFrame(table)}


class ExcelWriteTableNode(Node):
    type = "excel.write_table"
    category = "excel"
    name = "Excel Write Table"
    display_name = "写入 Excel 表格"
    description = "整块写入、追加或覆盖 Excel 工作表区域"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.SIDE_EFFECT
    tool_capability = ToolCapability.SIDE_EFFECT
    tool_exposed_params = ["sheet", "start", "mode"]
    inputs = (
        Port("workbook", "excel", "Excel Workbook 引用"),
        Port("table", "table", "要写入的表格"),
    )
    outputs = (Port("range", "excel", "已写入区域"),)
    params_schema = schema(
        {
            "sheet": {"type": "string", "description": "目标工作表"},
            "start": {"type": "string", "description": "起始单元格"},
            "mode": {"type": "string", "enum": ["overwrite", "append"], "description": "写入模式"},
            "header": {"type": "boolean", "description": "是否写表头"},
            "clear_below": {"type": "boolean", "description": "覆盖前清空下方旧内容"},
            "allow_formula": {"type": "boolean", "description": "是否允许公式字符串"},
            "autofit": {"type": "boolean", "description": "写后自适应列宽"},
            "preserve_format": {"type": "boolean", "description": "保留目标格式"},
            "fast_mode": {"type": "boolean", "description": "临时关闭刷新、事件和自动计算"},
        },
        ["sheet", "start", "mode"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        workbook = workbook_input(inputs, ctx)
        options = {
            key: params[key]
            for key in (
                "header",
                "clear_below",
                "allow_formula",
                "autofit",
                "preserve_format",
                "fast_mode",
            )
            if key in params
        }
        result = ctx.excel.call(
            ctx.run_id,
            "write_table",
            workbook,
            params["sheet"],
            params["start"],
            inputs["table"].to_arrow(),
            params["mode"],
            options,
        )
        return {"range": result}


class ExcelCellUpdateNode(Node):
    type = "excel.cell_update"
    category = "excel"
    name = "Excel Cell Update"
    display_name = "更新单元格"
    description = "原子更新若干不连续单元格，默认禁止公式"
    lane = Lane.TRUSTED_SERVICE
    inputs = (
        Port("workbook", "excel", "Excel Workbook 引用"),
        Port("table", "table", "含 address/value 列的可选表格"),
    )
    outputs = (Port("workbook", "excel", "Excel Workbook 引用"),)
    params_schema = schema(
        {
            "sheet": {"type": "string", "description": "目标工作表"},
            "cells": {
                "type": "array",
                "description": "单元格地址与值列表",
                "default": [],
                "items": {
                    "type": "object",
                    "description": "单个单元格更新",
                    "properties": {
                        "address": {"type": "string", "description": "单元格地址，例如 B2"},
                        "value": {"description": "要写入的单元格值"},
                    },
                    "required": ["address", "value"],
                },
            },
            "allow_formula": {"type": "boolean", "description": "是否允许公式"},
        },
        ["sheet"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        workbook = workbook_input(inputs, ctx)
        cells = list(params.get("cells", []))
        if "table" in inputs:
            cells.extend(inputs["table"].select(["address", "value"]).to_dicts())
        ctx.excel.call(
            ctx.run_id,
            "update_cells",
            workbook,
            params["sheet"],
            cells,
            params.get("allow_formula", False),
        )
        return {"workbook": workbook}


class ExcelSheetNamesNode(Node):
    type = "excel.sheet_names"
    category = "excel"
    name = "Excel Sheet Names"
    display_name = "列出工作表"
    description = "列出工作表名、索引与可见状态"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.VOLATILE
    inputs = (Port("workbook", "excel", "Excel Workbook 引用"),)
    outputs = (Port("table", "table", "工作表列表"),)
    params_schema = schema({})

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        values = ctx.excel.call(ctx.run_id, "sheet_names", workbook_input(inputs, ctx))
        return {"table": pl.DataFrame(values)}


class ExcelSheetNode(Node):
    type = "excel.sheet"
    category = "excel"
    name = "Excel Sheet"
    display_name = "工作表操作"
    description = "创建、删除、重命名或清空工作表"
    lane = Lane.TRUSTED_SERVICE
    inputs = (Port("workbook", "excel", "Excel Workbook 引用"),)
    outputs = (Port("workbook", "excel", "Excel Workbook 引用"),)
    params_schema = schema(
        {
            "action": {
                "type": "string",
                "enum": ["create", "delete", "rename", "clear"],
                "description": "工作表操作",
            },
            "name": {"type": "string", "description": "原工作表名"},
            "new_name": {"type": "string", "description": "重命名目标"},
        },
        ["action", "name"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        workbook = workbook_input(inputs, ctx)
        ctx.excel.call(
            ctx.run_id,
            "manage_sheet",
            workbook,
            params["action"],
            params["name"],
            params.get("new_name"),
        )
        return {"workbook": workbook}


class ExcelSaveNode(Node):
    type = "excel.save"
    category = "excel"
    name = "Excel Save"
    display_name = "保存工作簿"
    description = "显式保存或另存工作簿，不隐式覆盖文件"
    lane = Lane.TRUSTED_SERVICE
    inputs = (Port("workbook", "excel", "Excel Workbook 引用"),)
    outputs = (Port("path", "variable", "保存路径"),)
    params_schema = schema(
        {
            "mode": {"type": "string", "enum": ["save", "save_as"], "description": "保存方式"},
            "path": {"type": "string", "description": "相对 Root 的另存路径"},
            "format": {
                "type": "string",
                "enum": ["xlsx", "xlsm", "csv"],
                "description": "文件格式",
            },
            "overwrite": {"type": "boolean", "description": "是否允许覆盖已有文件"},
        },
        ["mode"],
    )
    portable_params = ["path"]

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        workbook = workbook_input(inputs, ctx)
        path = ctx.resolve(params["path"]) if params.get("path") else None
        result = ctx.excel.call(
            ctx.run_id,
            "save",
            workbook,
            params["mode"],
            path,
            params.get("format"),
            params.get("overwrite", False),
        )
        return {"path": str(result) if result is not None else None}


class ExcelRunMacroNode(Node):
    type = "excel.run_macro"
    category = "excel"
    name = "Excel Run Macro"
    display_name = "运行 Excel 宏"
    description = "通过 ExcelWorker 的 STA 串行队列调用 Application.Run"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.SIDE_EFFECT
    inputs = (Port("workbook", "excel", "目标工作簿"),)
    outputs = (Port("variable", "variable", "宏返回值"),)
    params_schema = schema(
        {
            "macro": {"type": "string", "description": "宏名，例如 Module1.Refresh"},
            "args": {
                "type": "array",
                "description": "按顺序传给宏的参数",
                "default": [],
                "items": {"description": "宏参数值"},
            },
        },
        ["macro"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        result = ctx.excel.call(
            ctx.run_id,
            "run_macro",
            workbook_input(inputs, ctx),
            params["macro"],
            params.get("args", []),
        )
        return {"variable": result}


EXCEL_NODES = (
    ExcelConnectNode,
    ExcelWorkbookNode,
    ExcelReadRangeNode,
    ExcelWriteTableNode,
    ExcelCellUpdateNode,
    ExcelSheetNamesNode,
    ExcelSheetNode,
    ExcelSaveNode,
    ExcelRunMacroNode,
)
