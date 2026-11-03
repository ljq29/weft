from __future__ import annotations

import ast
import io
import re
import shutil
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, ClassVar, cast

import polars as pl
from send2trash import send2trash
from weft_sdk import CachePolicy, DynamicPortGroup, Node, Port

from weft_worker.builtin import prop, schema, validate_table


class ExtraTableNode(Node):
    cache_policy = CachePolicy.PURE
    inputs: ClassVar[tuple[Port, ...]] = (Port("in", "table", "输入表格"),)
    outputs: ClassVar[tuple[Port, ...]] = (Port("out", "table", "输出表格"),)


class Joiner(ExtraTableNode):
    type = "table.joiner"
    category = "table"
    name = "Joiner"
    description = "按指定列连接两个表格"
    inputs = (Port("left", "table", "左表"), Port("right", "table", "右表"))
    params_schema = schema(
        {
            "how": prop(
                "string",
                "连接方式",
                enum=["inner", "left", "right", "outer", "cross", "anti", "semi"],
            ),
            "left_on": prop("string", "左表连接列"),
            "right_on": prop("string", "右表连接列"),
        },
        ["how", "left_on", "right_on"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {
            "out": inputs["left"].join(
                inputs["right"],
                how=params["how"],
                left_on=params["left_on"],
                right_on=params["right_on"],
                suffix="_right",
            )
        }


class Concatenate(ExtraTableNode):
    type = "table.concatenate"
    category = "table"
    name = "Concatenate"
    description = "按动态命名输入拼接表格"
    inputs = ()
    dynamic_inputs = (DynamicPortGroup("in_", "table", min_ports=2),)
    params_schema = schema(
        {
            "input_count": prop("integer", "输入端口数量", minimum=2, default=2),
            "how": prop(
                "string",
                "拼接方式",
                enum=["vertical", "horizontal", "diagonal"],
                default="vertical",
            ),
        }
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        tables = [
            inputs[key] for key in sorted(inputs, key=lambda key: int(key.removeprefix("in_")))
        ]
        if params.get("how", "vertical") == "horizontal":
            return {"out": pl.concat(tables, how="horizontal")}
        return {"out": pl.concat(tables, how=params.get("how", "vertical"))}


class GroupBy(ExtraTableNode):
    type = "table.groupby"
    category = "table"
    name = "GroupBy"
    description = "按分组列聚合表格"
    params_schema = schema(
        {
            "group_by": prop("array", "分组列"),
            "aggregations": prop("array", "聚合表达式列表"),
        },
        ["group_by", "aggregations"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        operations = []
        for item in params["aggregations"]:
            column = pl.col(item["column"])
            agg = item["agg"]
            if agg == "concat_str":
                expression = column.str.join("")
            elif agg == "count_distinct":
                expression = column.n_unique()
            elif agg == "count":
                expression = column.count()
            else:
                expression = getattr(column, agg)()
            operations.append(expression.alias(item.get("alias") or f"{item['column']}_{agg}"))
        return {"out": inputs["in"].group_by(params["group_by"]).agg(operations)}


class Pivot(ExtraTableNode):
    type = "table.pivot"
    category = "table"
    name = "Pivot"
    description = "将行透视成列"
    params_schema = schema(
        {
            "index": prop("array", "行索引列"),
            "columns": prop("string", "透视列"),
            "values": prop("string", "值列"),
            "agg": prop("string", "聚合方式"),
        },
        ["index", "columns", "values", "agg"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {
            "out": inputs["in"].pivot(
                index=params["index"],
                on=params["columns"],
                values=params["values"],
                aggregate_function=params["agg"],
            )
        }


class Unpivot(ExtraTableNode):
    type = "table.unpivot"
    category = "table"
    name = "Unpivot"
    description = "将列展开成行"
    params_schema = schema(
        {
            "index": prop("array", "保留索引列"),
            "on": prop("array", "展开列"),
            "variable_name": prop("string", "变量列名", default="variable"),
            "value_name": prop("string", "值列名", default="value"),
        }
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {
            "out": inputs["in"].unpivot(
                index=params.get("index", []),
                on=params.get("on", []),
                variable_name=params.get("variable_name", "variable"),
                value_name=params.get("value_name", "value"),
            )
        }


class DuplicateFilter(ExtraTableNode):
    type = "table.duplicate_filter"
    category = "table"
    name = "Duplicate Filter"
    description = "按列去重"
    params_schema = schema(
        {
            "columns": prop("array", "去重列，空为全部", default=[]),
            "keep": prop("string", "保留项", enum=["first", "last"], default="first"),
        }
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {
            "out": inputs["in"].unique(
                subset=params.get("columns") or None,
                keep=params.get("keep", "first"),
                maintain_order=True,
            )
        }


class MissingValue(ExtraTableNode):
    type = "table.missing_value"
    category = "table"
    name = "Missing Value"
    description = "按列处理缺失值"
    params_schema = schema({"strategies": prop("object", "每列的缺失值策略")}, ["strategies"])

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        table = inputs["in"]
        for column, rule in params["strategies"].items():
            action = rule["action"]
            if action == "drop_row":
                table = table.drop_nulls(subset=[column])
            elif action == "fill_const":
                table = table.with_columns(pl.col(column).fill_null(rule.get("value")))
            elif action == "fill_mean":
                table = table.with_columns(pl.col(column).fill_null(pl.col(column).mean()))
            else:
                table = table.with_columns(pl.col(column).fill_null(strategy="forward"))
        return {"out": table}


class TypeCast(ExtraTableNode):
    type = "table.type_cast"
    category = "table"
    name = "Type Cast"
    description = "转换列的数据类型"
    params_schema = schema(
        {
            "mapping": prop("object", "列到类型的映射"),
            "strict": prop("boolean", "失败是否报错", default=False),
        },
        ["mapping"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        types = {
            "int": pl.Int64,
            "float": pl.Float64,
            "str": pl.String,
            "bool": pl.Boolean,
            "date": pl.Date,
            "datetime": pl.Datetime,
        }
        expressions = []
        for column, kind in params["mapping"].items():
            expression = pl.col(column)
            if kind == "date":
                expression = expression.str.to_date(strict=params.get("strict", False))
            elif kind == "datetime":
                expression = expression.str.to_datetime(strict=params.get("strict", False))
            else:
                expression = expression.cast(types[kind], strict=params.get("strict", False))
            expressions.append(expression)
        return {"out": inputs["in"].with_columns(expressions)}


def compile_expression(source: str) -> pl.Expr:
    def convert(node: ast.AST) -> pl.Expr:
        if isinstance(node, ast.Expression):
            return convert(node.body)
        if isinstance(node, ast.Constant):
            return pl.lit(node.value)
        if isinstance(node, ast.List):
            return pl.lit([convert(item).meta for item in node.elts])
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)
        ):
            operation = {
                ast.Add: "__add__",
                ast.Sub: "__sub__",
                ast.Mult: "__mul__",
                ast.Div: "__truediv__",
                ast.Mod: "__mod__",
                ast.Pow: "__pow__",
            }[type(node.op)]
            return cast(pl.Expr, getattr(convert(node.left), operation)(convert(node.right)))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            value = convert(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            comparison_operation = {
                ast.Eq: "__eq__",
                ast.NotEq: "__ne__",
                ast.Gt: "__gt__",
                ast.GtE: "__ge__",
                ast.Lt: "__lt__",
                ast.LtE: "__le__",
            }.get(type(node.ops[0]))
            if comparison_operation:
                return cast(
                    pl.Expr,
                    getattr(convert(node.left), comparison_operation)(convert(node.comparators[0])),
                )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            args = [convert(arg) for arg in node.args]
            if name == "col" and len(args) == 1 and isinstance(node.args[0], ast.Constant):
                return pl.col(str(node.args[0].value))
            if name == "lit" and len(args) == 1:
                return args[0]
            if name in {"abs", "round", "sum", "min", "max", "len"}:
                return cast(pl.Expr, getattr(args[0], name)())
            raise ValueError(f"不允许调用函数 {name}")
        raise ValueError(f"表达式包含不允许的语法 {type(node).__name__}")

    return convert(ast.parse(source, mode="eval"))


class PolarsExpression(ExtraTableNode):
    type = "table.polars_expression"
    category = "table"
    name = "Polars Expression"
    description = "用 AST 白名单表达式新增列"
    params_schema = schema({"expressions": prop("array", "表达式与别名列表")}, ["expressions"])

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {
            "out": inputs["in"].with_columns(
                [
                    compile_expression(item["expr"]).alias(item["alias"])
                    for item in params["expressions"]
                ]
            )
        }


class MathFormula(ExtraTableNode):
    type = "table.math_formula"
    category = "table"
    name = "Math Formula"
    description = "用 $列名$ 语法新增计算列"
    params_schema = schema(
        {"formula": prop("string", "计算公式"), "alias": prop("string", "输出列别名")},
        ["formula", "alias"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        source = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)\$", r'col("\1")', params["formula"])
        return {"out": inputs["in"].with_columns(compile_expression(source).alias(params["alias"]))}


class StringManipulation(ExtraTableNode):
    type = "table.string_manipulation"
    category = "table"
    name = "String Manipulation"
    description = "执行常用字符串函数"
    params_schema = schema(
        {
            "column": prop("string", "输入列"),
            "operation": prop("string", "字符串操作"),
            "args": prop("array", "操作参数", default=[]),
            "alias": prop("string", "输出列别名"),
        },
        ["column", "operation", "alias"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        column = pl.col(params["column"]).str
        operation = params["operation"]
        args = params.get("args", [])
        operations: dict[str, Callable[[], pl.Expr]] = {
            "upper": column.to_uppercase,
            "lower": column.to_lowercase,
            "strip": column.strip_chars,
            "replace": lambda: column.replace(*args),
            "regex_replace": lambda: column.replace_all(*args),
            "substr": lambda: column.slice(*args),
            "concat": lambda: pl.concat_str([pl.col(params["column"]), *map(str, args)]),
            "pad": lambda: column.zfill(*args),
        }
        if operation not in operations:
            raise ValueError(f"未知字符串操作 {operation}")
        return {"out": inputs["in"].with_columns(operations[operation]().alias(params["alias"]))}


class TableToVariables(Node):
    type = "table.to_variables"
    category = "table"
    name = "Table to Variables"
    description = "将表格行或列转换为流变量"
    cache_policy = CachePolicy.PURE
    inputs = (Port("in", "table", "输入表格"),)
    outputs = (Port("variables", "variable", "流变量"),)
    params_schema = schema(
        {
            "row_index": prop("integer", "行索引", default=0),
            "mode": prop("string", "转换模式", enum=["row", "column_lists"], default="row"),
        }
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        table = inputs["in"]
        values = (
            {name: table[name].to_list() for name in table.columns}
            if params.get("mode") == "column_lists"
            else table.row(params.get("row_index", 0), named=True)
        )
        return {"variables": dict(values)}


class VariablesToTable(Node):
    type = "table.from_variables"
    category = "table"
    name = "Variables to Table"
    description = "将选中流变量转换为单行表"
    cache_policy = CachePolicy.PURE
    inputs = (Port("variables", "variable", "流变量"),)
    outputs = (Port("out", "table", "输出表格"),)
    params_schema = schema({"names": prop("array", "变量名列表")}, ["names"])

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {
            "out": pl.DataFrame([{name: inputs["variables"][name] for name in params["names"]}])
        }


class TableCreator(Node):
    type = "table.creator"
    category = "table"
    name = "Table Creator"
    description = "从参数中的行创建表格"
    cache_policy = CachePolicy.PURE
    outputs = (Port("out", "table", "输出表格"),)
    params_schema = schema({"rows": prop("array", "表格行数据")}, ["rows"])

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        table = pl.DataFrame(params["rows"])
        validate_table(table)
        return {"out": table}


class TableView(ExtraTableNode):
    type = "table.view"
    category = "table"
    name = "Table View"
    description = "在节点内预览输入表格"
    params_schema = schema({"rows": prop("integer", "节点内显示行数", default=10)})

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs["in"].head(params.get("rows", 10))}


class PathJoin(Node):
    type = "file.path_join"
    category = "file"
    name = "Path Join"
    description = "拼接并规范化路径"
    cache_policy = CachePolicy.PURE
    outputs = (Port("variables", "variable", "path 变量"),)
    params_schema = schema({"parts": prop("array", "路径片段")}, ["parts"])

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {"variables": {"path": str(Path(*params["parts"]))}}


class FileOperation(Node):
    cache_policy = CachePolicy.SIDE_EFFECT
    inputs = (Port("in", "table", "含 path 列的表格"),)
    outputs = (Port("variables", "variable", "操作结果"),)
    params_schema = schema(
        {
            "path": prop("string", "单文件路径"),
            "target": prop("string", "目标路径"),
            "overwrite": prop("boolean", "是否覆盖", default=False),
            "permanent": prop("boolean", "是否永久删除", default=False),
        }
    )

    def paths(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> list[Path]:
        if params.get("path"):
            return [ctx.resolve(params["path"])]
        return [ctx.resolve(row["path"]) for row in inputs["in"].to_dicts()]


class FileCopy(FileOperation):
    type = "file.copy"
    category = "file"
    name = "File Copy"
    description = "复制文件或目录"

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        for path in self.paths(ctx, inputs, params):
            target = ctx.resolve(params["target"])
            if target.exists() and not params.get("overwrite", False):
                raise FileExistsError(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.is_dir():
                shutil.copytree(path, target, dirs_exist_ok=True)
            else:
                shutil.copy2(path, target)
        return {"variables": {"count": len(self.paths(ctx, inputs, params))}}


class FileMove(FileOperation):
    type = "file.move"
    category = "file"
    name = "File Move"
    description = "移动文件或目录"

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        paths = self.paths(ctx, inputs, params)
        for path in paths:
            target = ctx.resolve(params["target"])
            if target.exists() and not params.get("overwrite", False):
                raise FileExistsError(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
        return {"variables": {"count": len(paths)}}


class FileRename(FileOperation):
    type = "file.rename"
    category = "file"
    name = "File Rename"
    description = "重命名文件或目录"

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        paths = self.paths(ctx, inputs, params)
        for path in paths:
            target = path.with_name(params["target"])
            if target.exists() and not params.get("overwrite", False):
                raise FileExistsError(target)
            path.rename(target)
        return {"variables": {"count": len(paths)}}


class FileDelete(FileOperation):
    type = "file.delete"
    category = "file"
    name = "File Delete"
    description = "移入回收站或永久删除"

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        paths = self.paths(ctx, inputs, params)
        for path in paths:
            if path.is_dir():
                shutil.rmtree(path) if params.get("permanent", False) else send2trash(path)
            elif params.get("permanent", False):
                path.unlink()
            else:
                send2trash(path)
        return {"variables": {"count": len(paths)}}


class PythonScript(Node):
    type = "code.python"
    category = "code"
    name = "Python Script"
    description = "在可信 Worker 中执行用户 Python 代码"
    params_schema = schema(
        {
            "source": prop("string", "代码来源", enum=["inline", "file"], default="inline"),
            "code": prop("string", "内联代码"),
            "path": prop("string", "代码文件路径"),
            "inputs": prop("array", "输入端口映射", default=[]),
            "outputs": prop("array", "输出端口声明", default=[]),
        }
    )

    def instantiated_inputs(self, params: dict[str, Any]) -> tuple[Port, ...]:
        return tuple(Port(item["port"], "table", "脚本输入") for item in params.get("inputs", []))

    def instantiated_outputs(self, params: dict[str, Any]) -> tuple[Port, ...]:
        return tuple(
            Port(item["port"], item["type"].lower(), "脚本输出")
            for item in params.get("outputs", [])
        )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        source = (
            params.get("code", "")
            if params.get("source", "inline") == "inline"
            else ctx.resolve(params["path"]).read_text(encoding="utf-8")
        )
        scope = {"inputs": inputs, "vars": dict(ctx.vars), "weft_ctx": ctx, "pl": pl}
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exec(compile(source, params.get("path", "<weft-script>"), "exec"), scope)
            if callable(scope.get("run")):
                values = scope["run"](inputs, dict(ctx.vars))
            else:
                values = scope
        if stdout.getvalue():
            ctx.log(stdout.getvalue().rstrip())
        result = {}
        for output in params.get("outputs", []):
            value = values.get(output["var"])
            expected = output["type"].lower()
            if expected == "table" and not isinstance(value, pl.DataFrame):
                raise TypeError(
                    f"Output '{output['var']}' expected Table, got {type(value).__name__}"
                )
            result[output["port"]] = value
        return result


BUILTIN_EXTRA_NODES = (
    Joiner,
    Concatenate,
    GroupBy,
    Pivot,
    Unpivot,
    DuplicateFilter,
    MissingValue,
    TypeCast,
    PolarsExpression,
    MathFormula,
    StringManipulation,
    TableToVariables,
    VariablesToTable,
    TableCreator,
    TableView,
    PathJoin,
    FileCopy,
    FileMove,
    FileRename,
    FileDelete,
    PythonScript,
)
