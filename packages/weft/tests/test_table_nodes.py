from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from weft.nodes.registry import builtin_registry
from weft_sdk import CachePolicy, weft_ctx


def execute(node_type: str, tmp_path: Path, params: dict, inputs: dict | None = None) -> dict:
    node = builtin_registry().get(node_type)
    with weft_ctx.activate(root=tmp_path, run_id="r_nodes"):
        return node.execute(weft_ctx, inputs or {}, params)


@pytest.mark.integration
def test_csv_parquet_json_read_write_and_overwrite(tmp_path: Path) -> None:
    """US-TBL-02/AC-1,3,4,5: table files round-trip with relative paths and overwrite rules."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "input.csv").write_text("name,amount\n甲,1\n乙,2\n", encoding="utf-8-sig")
    table = execute("table.read_csv", tmp_path, {"path": "data/input.csv"})["out"]
    assert table.to_dicts() == [{"name": "甲", "amount": 1}, {"name": "乙", "amount": 2}]
    for node_type, suffix in (
        ("table.write_csv", "csv"),
        ("table.write_parquet", "parquet"),
        ("table.write_json", "json"),
    ):
        execute(node_type, tmp_path, {"path": f"out/result.{suffix}"}, {"in": table})
        read_type = node_type.replace("write", "read")
        result = execute(read_type, tmp_path, {"path": f"out/result.{suffix}"})
        assert result["out"].to_dicts() == table.to_dicts()
        with pytest.raises(FileExistsError):
            execute(
                node_type,
                tmp_path,
                {"path": f"out/result.{suffix}", "overwrite": False},
                {"in": table},
            )


def test_csv_auto_gbk_and_separator(tmp_path: Path) -> None:
    """US-TBL-02/AC-1: CSV auto mode reads GBK and detects the separator."""
    (tmp_path / "gbk.csv").write_bytes("名称;金额\n测试;3\n".encode("gbk"))
    table = execute("table.read_csv", tmp_path, {"path": "gbk.csv"})["out"]
    assert table.to_dicts() == [{"名称": "测试", "金额": 3}]


def test_column_filter_supports_include_exclude_and_globs(tmp_path: Path) -> None:
    """US-TBL-03/AC-1,8: Column Filter supports globs and both modes."""
    table = pl.DataFrame({"id": [1], "amount_net": [2], "amount_gross": [3]})
    included = execute(
        "table.column_filter", tmp_path, {"mode": "include", "columns": ["amount_*"]}, {"in": table}
    )["out"]
    excluded = execute(
        "table.column_filter", tmp_path, {"mode": "exclude", "columns": ["amount_*"]}, {"in": table}
    )["out"]
    assert included.columns == ["amount_net", "amount_gross"]
    assert excluded.columns == ["id"]


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    [(">", "10", [20]), ("contains", "bc", ["abc"]), ("is_null", None, [None])],
)
def test_row_filter_operators(tmp_path: Path, operator: str, value: object, expected: list) -> None:
    """US-TBL-03/AC-2,8: Row Filter applies comparison, text and null predicates."""
    table = pl.DataFrame({"value": [10, 20, None], "text": ["abc", "x", None]})
    column = "text" if operator == "contains" else "value"
    result = execute(
        "table.row_filter",
        tmp_path,
        {"column": column, "operator": operator, "value": value},
        {"in": table},
    )["out"]
    assert result[column].to_list() == expected


def test_sorter_is_stable_and_rename_rejects_collision(tmp_path: Path) -> None:
    """US-TBL-03/AC-3,4,8: sorting is stable and rename collisions fail clearly."""
    table = pl.DataFrame({"group": [1, 1], "value": [2, 1]})
    sorted_table = execute(
        "table.sorter",
        tmp_path,
        {"keys": [{"column": "value", "descending": False}]},
        {"in": table},
    )["out"]
    assert sorted_table["value"].to_list() == [1, 2]
    renamed = execute(
        "table.column_rename", tmp_path, {"mapping": {"value": "amount"}}, {"in": table}
    )["out"]
    assert renamed.columns == ["group", "amount"]
    with pytest.raises(ValueError, match="目标列名已存在"):
        execute("table.column_rename", tmp_path, {"mapping": {"value": "group"}}, {"in": table})


def test_variables_row_count_and_list_files(tmp_path: Path) -> None:
    """US-TBL-06/AC-3,4, US-TBL-07/AC-1: variables, counts and file listings."""
    variables = execute(
        "flow.variable",
        tmp_path,
        {"values": [{"name": "file", "type": "path", "value": "data/a.csv"}]},
    )["variables"]
    assert variables["file"] == str(tmp_path / "data/a.csv")
    table = pl.DataFrame({"value": [1, 2]})
    count = execute("table.row_count", tmp_path, {}, {"in": table})["variables"]
    assert count == {"row_count": 2}
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "a.xlsx").write_bytes(b"a")
    (tmp_path / "inbox" / "b.txt").write_bytes(b"b")
    files = execute(
        "file.list", tmp_path, {"path": "inbox", "pattern": "*.xlsx", "recursive": False}
    )["out"]
    assert files.to_dicts()[0]["path"] == "inbox/a.xlsx"
    assert files.to_dicts()[0]["name"] == "a.xlsx"


def test_builtin_cache_policy_matrix() -> None:
    """US-EXE-04/AC-11: built-in read/transform, write and directory cache policies are explicit."""
    registry = builtin_registry()
    for node_type in (
        "table.read_csv",
        "table.read_parquet",
        "table.read_json",
        "table.column_filter",
        "table.row_filter",
        "table.sorter",
        "table.column_rename",
        "file.list",
    ):
        assert registry.get(node_type).cache_policy == CachePolicy.PURE
    for node_type in ("table.write_csv", "table.write_parquet", "table.write_json"):
        assert registry.get(node_type).cache_policy == CachePolicy.SIDE_EFFECT
    assert registry.get("table.read_csv").cache_inputs[0].kind == "file"
    assert registry.get("file.list").cache_inputs[0].kind == "directory"
