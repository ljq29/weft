from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from weft import __version__
from weft.engine.scheduler import schema_with_variables
from weft.nodes.export import main, render_markdown, render_node_index
from weft.nodes.registry import NodeRegistry, builtin_registry, implementation_hash


def test_builtin_schemas_are_draft_2020_12() -> None:
    """US-DES-04/AC-4: every registered node schema is valid JSON Schema 2020-12."""
    registry = builtin_registry()
    assert registry.get("flow.trigger").type == "flow.trigger"
    for node in registry.all():
        assert node.params_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        jsonschema.Draft202012Validator.check_schema(node.params_schema)
        assert node.description
        for prop in node.params_schema.get("properties", {}).values():
            assert prop.get("description")


def schema_at(node_type: str, path: str) -> Any:
    current: Any = builtin_registry().get(node_type).params_schema
    for key in path.split("."):
        current = current[key]
    return current


@pytest.mark.parametrize(
    ("node_type", "path", "fields", "required"),
    [
        (
            "flow.trigger",
            "properties.schedule.properties.schedules.items",
            ("cron", "interval_seconds"),
            (),
        ),
        (
            "flow.trigger",
            "properties.watch.properties.watches.items",
            ("path", "pattern", "events", "recursive", "debounce_ms"),
            ("path",),
        ),
        (
            "table.groupby",
            "properties.aggregations.items",
            ("column", "agg", "alias"),
            ("column", "agg"),
        ),
        ("table.sorter", "properties.keys.items", ("column", "descending"), ("column",)),
        (
            "flow.variable",
            "properties.values.items",
            ("name", "type", "value"),
            ("name", "type"),
        ),
        (
            "table.polars_expression",
            "properties.expressions.items",
            ("expr", "alias"),
            ("expr", "alias"),
        ),
        (
            "table.rule_engine",
            "properties.rules.items",
            ("condition", "value"),
            ("condition",),
        ),
        (
            "excel.cell_update",
            "properties.cells.items",
            ("address", "value"),
            ("address", "value"),
        ),
        ("code.python", "properties.inputs.items", ("port", "var"), ("port", "var")),
        (
            "code.python",
            "properties.outputs.items",
            ("var", "port", "type"),
            ("var", "port", "type"),
        ),
    ],
)
def test_builtin_record_arrays_expose_item_schemas(
    node_type: str, path: str, fields: tuple[str, ...], required: tuple[str, ...]
) -> None:
    """US-DES-04/AC-4: record arrays expose editable object fields and required keys."""
    item = schema_at(node_type, path)
    assert item["type"] == "object"
    assert set(fields) <= set(item["properties"])
    assert set(required) <= set(item.get("required", []))
    for field in item["properties"].values():
        assert field.get("description")


@pytest.mark.parametrize(
    ("node_type", "path"),
    [
        ("table.column_filter", "properties.columns"),
        ("table.groupby", "properties.group_by"),
        ("table.pivot", "properties.index"),
        ("table.unpivot", "properties.index"),
        ("table.unpivot", "properties.on"),
        ("table.duplicate_filter", "properties.columns"),
        ("table.from_variables", "properties.names"),
        ("file.path_join", "properties.parts"),
        ("agent.node_tool", "properties.exposed_params"),
        ("agent.sandboxed_tools", "properties.tools"),
        ("agent.pi", "properties.extra_args"),
    ],
)
def test_builtin_string_arrays_expose_items(node_type: str, path: str) -> None:
    """US-DES-04/AC-4: common string arrays expose item schemas to the generic form."""
    array = schema_at(node_type, path)
    assert array["type"] == "array"
    assert array["items"]["type"] == "string"
    assert array["items"]["description"]


def test_builtin_nested_and_mapping_schemas_cover_values() -> None:
    """US-DES-04/AC-4: nested events, conditions, mappings and dynamic rows have value schemas."""
    events = schema_at(
        "flow.trigger", "properties.watch.properties.watches.items.properties.events"
    )
    assert events["items"]["type"] == "string"
    assert set(events["default"]) <= set(events["items"]["enum"])

    condition = schema_at("table.rule_engine", "properties.rules.items.properties.condition")
    assert condition["type"] == "object"
    assert set(condition["properties"]) == {"column", "operator", "value"}
    assert "is_null" in condition["properties"]["operator"]["enum"]

    for node_type, path in [
        ("table.column_rename", "properties.mapping"),
        ("table.type_cast", "properties.mapping"),
        ("flow.http_response", "properties.headers"),
        ("flow.switch", "properties.cases"),
        ("excel.read_range", "properties.dtype_hints"),
    ]:
        value = schema_at(node_type, path)["additionalProperties"]
        assert value["type"] == "string"
        assert value["description"]

    strategy = schema_at("table.missing_value", "properties.strategies")["additionalProperties"]
    assert strategy["type"] == "object"
    assert strategy["required"] == ["action"]
    assert set(strategy["properties"]["action"]["enum"]) == {
        "drop_row",
        "fill_const",
        "fill_mean",
        "fill_prev",
    }

    environment = schema_at("code.shell", "properties.env")["additionalProperties"]
    assert environment["description"]
    assert "type" not in environment

    row = schema_at("table.creator", "properties.rows.items")
    assert row["type"] == "object"
    assert row["additionalProperties"]["description"]
    assert "type" not in row["additionalProperties"]


@pytest.mark.parametrize(
    ("node_type", "params"),
    [
        (
            "flow.trigger",
            {
                "schedule": {"schedules": [{"cron": "0 9 * * 1"}, {"interval_seconds": 30}]},
                "watch": {
                    "watches": [
                        {
                            "path": "data",
                            "events": ["created", "modified"],
                            "recursive": True,
                            "debounce_ms": 50,
                        }
                    ]
                },
            },
        ),
        (
            "table.groupby",
            {
                "group_by": ["region"],
                "aggregations": [{"column": "amount", "agg": "sum", "alias": "total"}],
            },
        ),
        ("table.sorter", {"keys": [{"column": "amount", "descending": True}]}),
        (
            "flow.variable",
            {
                "values": [
                    {"name": "threshold", "type": "int", "value": 10},
                    {"name": "optional", "type": "str"},
                ]
            },
        ),
        (
            "table.polars_expression",
            {"expressions": [{"expr": 'col("amount") * 1.1', "alias": "gross"}]},
        ),
        (
            "table.rule_engine",
            {
                "rules": [
                    {
                        "condition": {"column": "amount", "operator": ">", "value": 10},
                        "value": "large",
                    }
                ],
                "alias": "size",
            },
        ),
        (
            "excel.cell_update",
            {"sheet": "Sheet1", "cells": [{"address": "B2", "value": 42}]},
        ),
        (
            "code.python",
            {
                "inputs": [{"port": "in", "var": "df"}],
                "outputs": [{"var": "df", "port": "out", "type": "Table"}],
            },
        ),
        ("table.creator", {"rows": [{"name": "a", "value": 1, "tags": ["x"]}]}),
        ("table.missing_value", {"strategies": {"value": {"action": "fill_const", "value": 0}}}),
        ("table.type_cast", {"mapping": {"amount": "float", "active": "bool"}}),
        ("code.shell", {"command": "pwd", "env": {"RETRIES": 3, "FLAGS": ["a", "b"]}}),
        ("flow.http_response", {"headers": {"Content-Type": "application/json"}}),
        ("flow.switch", {"variable": "kind", "cases": {"a": "case_1"}}),
        ("excel.read_range", {"sheet": "Sheet1", "dtype_hints": {"amount": "float64"}}),
    ],
)
def test_structured_schemas_accept_existing_parameter_shapes(
    node_type: str, params: dict[str, Any]
) -> None:
    """US-DES-04/AC-4: richer declarations remain compatible with existing runtime values."""
    declaration = builtin_registry().get(node_type)
    jsonschema.validate(params, schema_with_variables(declaration.params_schema))


def test_builtin_nodes_have_chinese_display_names() -> None:
    """US-DES-02/AC-1: built-ins expose independent Chinese names alongside canonical names."""
    nodes = builtin_registry().all()
    assert len(nodes) == 64
    for node in nodes:
        assert node.name
        assert node.display_name != node.name
        assert any("\u4e00" <= char <= "\u9fff" for char in node.display_name)
        manifest = node.manifest({})
        assert manifest["name"] == node.name
        assert manifest["display_name"] == node.display_name


def test_custom_nodes_can_be_registered_and_exported() -> None:
    """T1.3: registry declarations flow into the generated node index."""
    registry = NodeRegistry()
    registry.register(builtin_registry().get("flow.trigger").__class__)
    exported = json.loads(render_node_index(registry))
    assert exported["nodes"][0]["type"] == "flow.trigger"
    assert exported["nodes"][0]["params_schema"]["type"] == "object"


def test_node_implementation_hash_has_versioned_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T7.10: nodes retain deterministic cache keys when Python source is unavailable."""
    monkeypatch.setattr(
        "weft.nodes.registry.inspect.getsource", lambda _: (_ for _ in ()).throw(OSError())
    )
    node_type = builtin_registry().get("flow.trigger").__class__
    expected = f"weft.nodes.flow.TriggerNode@{__version__}".encode()
    assert (
        implementation_hash(node_type)
        == f"sha256:{__import__('hashlib').sha256(expected).hexdigest()}"
    )


def test_duplicate_node_registration_is_rejected() -> None:
    """T1.3: a registry cannot silently replace an existing node declaration."""
    registry = builtin_registry()
    with pytest.raises(ValueError, match="already registered"):
        registry.register(registry.get("flow.trigger").__class__)


def test_generated_markdown_matches_repository(tmp_path: Path) -> None:
    """T1.3: generated node docs are stable and --check detects manual edits."""
    expected = render_markdown(builtin_registry())
    output = tmp_path / "09-nodes-v1.md"
    assert main(["--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == expected
    assert main(["--output", str(output), "--check"]) == 0
    output.write_text(expected + "manual edit\n", encoding="utf-8")
    assert main(["--output", str(output), "--check"]) == 1
