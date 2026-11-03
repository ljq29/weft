from __future__ import annotations

import csv
import fnmatch
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from weft_sdk import CachePolicy, ExternalInput, Node, Port, ToolCapability


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


def prop(kind: str, description: str, **extra: Any) -> dict[str, Any]:
    return {"type": kind, "description": description, **extra}


def validate_table(table: pl.DataFrame) -> None:
    if any(not name for name in table.columns):
        raise ValueError("列名不能为空")
    if len(table.columns) != len(set(table.columns)):
        raise ValueError("列名不能重复")


class TableNode(Node):
    cache_policy = CachePolicy.PURE
    outputs = (Port("out", "table", "输出表格"),)

    def validate(self, table: pl.DataFrame) -> pl.DataFrame:
        validate_table(table)
        return table


class ReadCSV(TableNode):
    type = "table.read_csv"
    category = "table"
    name = "Read CSV"
    description = "读取 CSV 文件为表格"
    params_schema = schema(
        {
            "path": prop("string", "CSV 文件路径"),
            "encoding": prop("string", "编码", default="auto"),
            "separator": prop("string", "分隔符", default="auto"),
            "header": prop("boolean", "是否含表头", default=True),
            "skip_rows": prop("integer", "跳过行数", default=0),
        },
        ["path"],
    )
    cache_inputs = [ExternalInput("path", "file")]

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        data = ctx.resolve(params["path"]).read_bytes()
        encodings = (
            ["utf-8-sig", "utf-8", "gbk"]
            if params.get("encoding", "auto") == "auto"
            else [params["encoding"]]
        )
        last_error: UnicodeDecodeError | None = None
        for encoding in encodings:
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError as error:
                last_error = error
        else:
            raise ValueError("无法识别 CSV 编码") from last_error
        separator = params.get("separator", "auto")
        if separator == "auto":
            try:
                separator = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
            except csv.Error:
                separator = ","
        table = pl.read_csv(
            io.StringIO(text),
            separator=separator,
            has_header=params.get("header", True),
            skip_rows=params.get("skip_rows", 0),
        )
        return {"out": self.validate(table)}


class ReadParquet(TableNode):
    type = "table.read_parquet"
    category = "table"
    name = "Read Parquet"
    description = "读取 Parquet 文件"
    params_schema = schema({"path": prop("string", "Parquet 文件路径")}, ["path"])
    cache_inputs = [ExternalInput("path", "file")]

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {"out": self.validate(pl.read_parquet(ctx.resolve(params["path"])))}


class ReadJSON(TableNode):
    type = "table.read_json"
    category = "table"
    name = "Read JSON"
    description = "读取 JSON 数组或 JSON Lines 文件"
    params_schema = schema({"path": prop("string", "JSON 文件路径")}, ["path"])
    cache_inputs = [ExternalInput("path", "file")]

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        text = ctx.resolve(params["path"]).read_text(encoding="utf-8")
        table = (
            pl.read_json(io.StringIO(text))
            if text.lstrip().startswith("[")
            else pl.read_ndjson(io.StringIO(text))
        )
        return {"out": self.validate(table)}


class WriteTable(Node):
    cache_policy = CachePolicy.SIDE_EFFECT
    inputs = (Port("in", "table", "输入表格"),)
    params_schema = schema(
        {
            "path": prop("string", "输出文件路径"),
            "overwrite": prop("boolean", "是否覆盖已有文件", default=True),
        },
        ["path"],
    )

    def target(self, ctx: Any, params: dict[str, Any]) -> Path:
        path = Path(ctx.resolve(params["path"]))
        if path.exists() and not params.get("overwrite", True):
            raise FileExistsError(f"文件已存在：{path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class WriteCSV(WriteTable):
    type = "table.write_csv"
    category = "table"
    name = "Write CSV"
    description = "将表格写入 CSV 文件"
    params_schema = schema(
        {
            "path": prop("string", "输出文件路径"),
            "encoding": prop("string", "编码", default="utf-8-sig"),
            "separator": prop("string", "分隔符", default=","),
            "overwrite": prop("boolean", "是否覆盖已有文件", default=True),
        },
        ["path"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        path = self.target(ctx, params)
        text = inputs["in"].write_csv(separator=params.get("separator", ","))
        path.write_bytes(text.encode(params.get("encoding", "utf-8-sig")))
        return {}


class WriteParquet(WriteTable):
    type = "table.write_parquet"
    category = "table"
    name = "Write Parquet"
    description = "将表格写入 Parquet 文件"

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        inputs["in"].write_parquet(self.target(ctx, params))
        return {}


class WriteJSON(WriteTable):
    type = "table.write_json"
    category = "table"
    name = "Write JSON"
    description = "将表格写入 JSON 数组或 JSON Lines"
    params_schema = schema(
        {
            "path": prop("string", "输出文件路径"),
            "lines": prop("boolean", "是否使用 JSON Lines", default=False),
            "overwrite": prop("boolean", "是否覆盖已有文件", default=True),
        },
        ["path"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        path = self.target(ctx, params)
        if params.get("lines", False):
            inputs["in"].write_ndjson(path)
        else:
            inputs["in"].write_json(path)
        return {}


class ColumnFilter(TableNode):
    type = "table.column_filter"
    category = "table"
    name = "Column Filter"
    description = "按名称或通配符筛选列"
    inputs = (Port("in", "table", "输入表格"),)
    params_schema = schema(
        {
            "mode": prop("string", "包含或排除", enum=["include", "exclude"]),
            "columns": prop("array", "列名或通配符列表"),
        },
        ["mode", "columns"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        table = inputs["in"]
        selected = [
            name
            for name in table.columns
            if any(fnmatch.fnmatchcase(name, pattern) for pattern in params["columns"])
        ]
        if params["mode"] == "exclude":
            selected = [name for name in table.columns if name not in selected]
        return {"out": table.select(selected)}


class RowFilter(TableNode):
    type = "table.row_filter"
    category = "table"
    name = "Row Filter"
    description = "按单条件筛选行"
    tool_capability = ToolCapability.READ_ONLY
    tool_exposed_params = ["column", "operator", "value"]
    inputs = (Port("in", "table", "输入表格"), Port("variables", "variable", "流变量"))
    params_schema = schema(
        {
            "column": prop("string", "列名"),
            "operator": prop(
                "string",
                "比较操作",
                enum=[
                    "==",
                    "!=",
                    ">",
                    ">=",
                    "<",
                    "<=",
                    "contains",
                    "starts_with",
                    "regex",
                    "is_null",
                    "is_not_null",
                    "in",
                ],
            ),
            "value": {"description": "比较值"},
        },
        ["column", "operator"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        table = inputs["in"]
        column = pl.col(params["column"])
        operator = params["operator"]
        value = params.get("value")
        if operator in {"is_null", "is_not_null"}:
            expression = column.is_null() if operator == "is_null" else column.is_not_null()
        else:
            try:
                value = json.loads(value) if isinstance(value, str) else value
            except json.JSONDecodeError:
                pass
            if operator in {"==", "!=", ">", ">=", "<", "<="}:
                operations = {"==": "eq", "!=": "ne", ">": "gt", ">=": "ge", "<": "lt", "<=": "le"}
                expression = getattr(column, operations[operator])(value)
            elif operator == "contains":
                expression = column.str.contains(str(value), literal=True)
            elif operator == "starts_with":
                expression = column.str.starts_with(str(value))
            elif operator == "regex":
                expression = column.str.contains(str(value))
            else:
                values = value if isinstance(value, list) else str(value).split(",")
                expression = column.is_in(values)
        return {"out": table.filter(expression)}


class Sorter(TableNode):
    type = "table.sorter"
    category = "table"
    name = "Sorter"
    description = "按多个列键稳定排序"
    inputs = (Port("in", "table", "输入表格"),)
    params_schema = schema({"keys": prop("array", "排序列与方向列表")}, ["keys"])

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        keys = params["keys"]
        return {
            "out": inputs["in"].sort(
                by=[item["column"] for item in keys],
                descending=[item.get("descending", False) for item in keys],
                maintain_order=True,
            )
        }


class ColumnRename(TableNode):
    type = "table.column_rename"
    category = "table"
    name = "Column Rename"
    description = "重命名表格列"
    inputs = (Port("in", "table", "输入表格"),)
    params_schema = schema({"mapping": prop("object", "旧列名到新列名映射")}, ["mapping"])

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        mapping = params["mapping"]
        existing = set(inputs["in"].columns)
        if any(target in existing and target not in mapping for target in mapping.values()):
            raise ValueError("目标列名已存在")
        return {"out": inputs["in"].rename(mapping)}


class VariableNode(Node):
    type = "flow.variable"
    category = "flow"
    name = "Variable"
    description = "定义流变量"
    cache_policy = CachePolicy.PURE
    inputs = (Port("variables", "variable", "上游流变量"),)
    outputs = (Port("variables", "variable", "流变量"),)
    params_schema = schema({"values": prop("array", "变量定义列表")}, ["values"])

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        result = {}
        for item in params["values"]:
            value = item.get("value")
            if item["type"] == "path":
                value = str(ctx.resolve(value))
            result[item["name"]] = value
        return {"variables": result}


class TableRowCount(Node):
    type = "table.row_count"
    category = "table"
    name = "Table Row Count"
    description = "输出表格行数变量"
    cache_policy = CachePolicy.PURE
    inputs = (Port("in", "table", "输入表格"),)
    outputs = (Port("variables", "variable", "row_count 变量"),)

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {"variables": {"row_count": inputs["in"].height}}


class ListFiles(TableNode):
    type = "file.list"
    category = "file"
    name = "List Files"
    description = "列出目录中的文件与目录"
    params_schema = schema(
        {
            "path": prop("string", "目录路径"),
            "pattern": prop("string", "glob 过滤", default="*"),
            "recursive": prop("boolean", "是否递归", default=False),
        },
        ["path"],
    )
    cache_inputs = [ExternalInput("path", "directory")]

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        root = ctx.resolve(params["path"])
        paths = root.rglob("*") if params.get("recursive", False) else root.glob("*")
        rows = []
        for path in sorted(paths):
            if not path.match(params.get("pattern", "*")):
                continue
            stat = path.stat()
            rows.append(
                {
                    "path": path.relative_to(ctx.root).as_posix()
                    if path.is_relative_to(ctx.root)
                    else str(path),
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                    "is_dir": path.is_dir(),
                }
            )
        return {"out": pl.DataFrame(rows)}


BUILTIN_NODES = (
    ReadCSV,
    ReadParquet,
    ReadJSON,
    WriteCSV,
    WriteParquet,
    WriteJSON,
    ColumnFilter,
    RowFilter,
    Sorter,
    ColumnRename,
    VariableNode,
    TableRowCount,
    ListFiles,
)
