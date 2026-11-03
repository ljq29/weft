from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from weft.nodes.registry import builtin_registry
from weft_sdk import CachePolicy, weft_ctx


def execute(node_type: str, tmp_path: Path, params: dict, inputs: dict | None = None) -> dict:
    with weft_ctx.activate(root=tmp_path, run_id="r_extra"):
        return builtin_registry().get(node_type).execute(weft_ctx, inputs or {}, params)


def test_join_concat_group_pivot_and_unpivot(tmp_path: Path) -> None:
    """US-TBL-04/AC-1,2,3,4: combination nodes produce expected small-table results."""
    left = pl.DataFrame({"id": [1, 2], "amount": [10, 20]})
    right = pl.DataFrame({"id": [1, 2], "region": ["a", "b"]})
    joined = execute(
        "table.joiner",
        tmp_path,
        {"how": "inner", "left_on": "id", "right_on": "id"},
        {"left": left, "right": right},
    )["out"]
    assert joined["region"].to_list() == ["a", "b"]
    concatenated = execute(
        "table.concatenate",
        tmp_path,
        {"input_count": 2, "how": "vertical"},
        {"in_1": left, "in_2": left},
    )["out"]
    assert concatenated.height == 4
    grouped = execute(
        "table.groupby",
        tmp_path,
        {
            "group_by": ["region"],
            "aggregations": [{"column": "amount", "agg": "sum", "alias": "total"}],
        },
        {"in": joined},
    )["out"]
    assert grouped.sort("region")["total"].to_list() == [10, 20]
    pivot = execute(
        "table.pivot",
        tmp_path,
        {"index": ["id"], "columns": "region", "values": "amount", "agg": "sum"},
        {"in": joined},
    )["out"]
    assert pivot.columns == ["id", "a", "b"]
    unpivoted = execute(
        "table.unpivot", tmp_path, {"index": ["id"], "on": ["a", "b"]}, {"in": pivot}
    )["out"]
    assert unpivoted.height == 4


def test_duplicate_missing_and_type_cast(tmp_path: Path) -> None:
    """US-TBL-03/AC-5,6,7,8: deduplication, null handling and type casts work."""
    table = pl.DataFrame({"id": [1, 1, 2], "value": ["1", None, "3"]})
    deduplicated = execute(
        "table.duplicate_filter", tmp_path, {"columns": ["id"], "keep": "first"}, {"in": table}
    )["out"]
    assert deduplicated.height == 2
    filled = execute(
        "table.missing_value",
        tmp_path,
        {"strategies": {"value": {"action": "fill_const", "value": "0"}}},
        {"in": table},
    )["out"]
    assert filled["value"].to_list() == ["1", "0", "3"]
    cast = execute("table.type_cast", tmp_path, {"mapping": {"value": "int"}}, {"in": filled})[
        "out"
    ]
    assert cast["value"].dtype == pl.Int64
    with pytest.raises(pl.exceptions.PolarsError):
        execute(
            "table.type_cast",
            tmp_path,
            {"mapping": {"id": "int"}, "strict": True},
            {"in": pl.DataFrame({"id": ["bad"]})},
        )


def test_expressions_math_string_and_ast_rejections(tmp_path: Path) -> None:
    """US-TBL-05/AC-1,2,3,5: expressions work while arbitrary Python is rejected."""
    table = pl.DataFrame({"amount": [10, 20], "text": [" a ", " b "]})
    result = execute(
        "table.polars_expression",
        tmp_path,
        {"expressions": [{"alias": "taxed", "expr": 'col("amount") * 1.1'}]},
        {"in": table},
    )["out"]
    assert result["taxed"].to_list() == [11.0, 22.0]
    math = execute(
        "table.math_formula",
        tmp_path,
        {"formula": "$amount$ * 2", "alias": "double"},
        {"in": table},
    )["out"]
    assert math["double"].to_list() == [20, 40]
    upper = execute(
        "table.string_manipulation",
        tmp_path,
        {"column": "text", "operation": "upper", "args": [], "alias": "upper"},
        {"in": table},
    )["out"]
    assert upper["upper"].to_list() == [" A ", " B "]
    for source in ('__import__("os")', 'col("amount").__class__', 'open("x")'):
        with pytest.raises(ValueError):
            execute(
                "table.polars_expression",
                tmp_path,
                {"expressions": [{"alias": "bad", "expr": source}]},
                {"in": table},
            )


def test_variables_creator_view_and_path_join(tmp_path: Path) -> None:
    """US-TBL-06/AC-1,2, US-TBL-10/AC-1,2, US-TBL-07/AC-3: conversions and helper nodes work."""
    table = pl.DataFrame({"name": ["a"], "amount": [2]})
    variables = execute("table.to_variables", tmp_path, {"row_index": 0}, {"in": table})[
        "variables"
    ]
    assert variables == {"name": "a", "amount": 2}
    converted = execute(
        "table.from_variables", tmp_path, {"names": ["name", "amount"]}, {"variables": variables}
    )["out"]
    assert converted.to_dicts() == [{"name": "a", "amount": 2}]
    created = execute("table.creator", tmp_path, {"rows": [{"x": 1}]})["out"]
    assert created.to_dicts() == [{"x": 1}]
    viewed = execute("table.view", tmp_path, {"rows": 10}, {"in": table})["out"]
    assert viewed.to_dicts() == table.to_dicts()
    joined = execute("file.path_join", tmp_path, {"parts": ["data", "a.csv"]})["variables"]
    assert joined["path"] == str(Path("data") / "a.csv")


def test_file_copy_move_rename_and_delete(tmp_path: Path) -> None:
    """US-TBL-07/AC-2,3,4,5: trusted file operations work on relative paths."""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    execute("file.copy", tmp_path, {"path": "a.txt", "target": "out/a.txt"})
    assert (tmp_path / "out" / "a.txt").read_text(encoding="utf-8") == "a"
    execute("file.move", tmp_path, {"path": "out/a.txt", "target": "out/b.txt"})
    assert not (tmp_path / "out" / "a.txt").exists()
    execute("file.rename", tmp_path, {"path": "out/b.txt", "target": "c.txt"})
    assert (tmp_path / "out" / "c.txt").exists()
    execute("file.delete", tmp_path, {"path": "out/c.txt", "permanent": True})
    assert not (tmp_path / "out" / "c.txt").exists()


def test_python_script_inline_run_dynamic_ports_and_type_error(tmp_path: Path) -> None:
    """US-TBL-08/AC-1,2,3,6: Python scripts support inline/run forms and dynamic typed ports."""
    table = pl.DataFrame({"value": [1]})
    params = {
        "source": "inline",
        "code": (
            "def run(inputs, vars):\n"
            "    return {'df': inputs['in'].with_columns(pl.col('value') + 1)}\n"
        ),
        "inputs": [{"port": "in", "var": "df"}],
        "outputs": [{"var": "df", "port": "out", "type": "Table"}],
    }
    node = builtin_registry().get("code.python")
    assert [port.name for port in node.instantiated_inputs(params)] == ["in"]
    assert [port.name for port in node.instantiated_outputs(params)] == ["out"]
    result = execute("code.python", tmp_path, params, {"in": table})["out"]
    assert result["value"].to_list() == [2]
    params["code"] = "df = 'wrong'"
    with pytest.raises(TypeError, match="expected Table"):
        execute("code.python", tmp_path, params, {"in": table})


def test_rule_engine_first_match_default_and_shared_conditions(tmp_path: Path) -> None:
    """US-TBL-05/AC-4: ordered rules share Row Filter semantics and preserve defaults."""
    table = pl.DataFrame({"amount": [-5, 5, 15, None], "text": ["abc", "x", "abc", None]})
    result = execute(
        "table.rule_engine",
        tmp_path,
        {
            "rules": [
                {
                    "condition": {"column": "amount", "operator": ">", "value": "10"},
                    "value": "high",
                },
                {
                    "condition": {"column": "amount", "operator": ">", "value": "0"},
                    "value": "positive",
                },
                {"condition": {"column": "amount", "operator": "is_null"}, "value": "missing"},
                {
                    "condition": {"column": "text", "operator": "contains", "value": "bc"},
                    "value": "text",
                },
            ],
            "default": "low",
            "alias": "category",
        },
        {"in": table},
    )["out"]
    assert result["category"].to_list() == ["text", "positive", "high", "missing"]
    assert builtin_registry().get("table.rule_engine").cache_policy == CachePolicy.PURE


def test_extra_cache_policy_matrix() -> None:
    """US-EXE-04/AC-11: extra transforms are pure and file mutations are side effects."""
    registry = builtin_registry()
    for node_type in ("table.joiner", "table.concatenate", "table.groupby", "table.creator"):
        assert registry.get(node_type).cache_policy == CachePolicy.PURE
    for node_type in ("file.copy", "file.move", "file.rename", "file.delete", "code.python"):
        assert registry.get(node_type).cache_policy == CachePolicy.SIDE_EFFECT


def test_python_script_print_and_file_source(tmp_path: Path) -> None:
    """US-TBL-08/AC-4,5,6: print becomes a log and file source uses the Root."""
    (tmp_path / "nodes").mkdir()
    (tmp_path / "nodes" / "script.py").write_text("print('hello')\nvalue = 7\n", encoding="utf-8")
    logs = []
    with weft_ctx.activate(
        root=tmp_path, run_id="r_python", log=lambda level, message: logs.append((level, message))
    ):
        result = (
            builtin_registry()
            .get("code.python")
            .execute(
                weft_ctx,
                {},
                {
                    "source": "file",
                    "path": "nodes/script.py",
                    "outputs": [{"var": "value", "port": "value", "type": "Variable"}],
                },
            )
        )
    assert result["value"] == 7
    assert logs == [("INFO", "hello")]
