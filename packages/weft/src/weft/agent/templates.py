from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import polars as pl
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment


class TemplateSandbox(SandboxedEnvironment):
    def is_safe_attribute(self, obj: Any, attr: str, value: Any) -> bool:
        return False


def markdown_table(table: pl.DataFrame, max_rows: int) -> str:
    def text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False).replace("|", "\\|")
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    rows = table.head(max_rows).rows()
    lines = [
        "| " + " | ".join(text(column) for column in table.columns) + " |",
        "| " + " | ".join("---" for _ in table.columns) + " |",
    ]
    lines.extend("| " + " | ".join(text(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def render_template(
    source: str,
    variables: Mapping[str, Any],
    tables: Mapping[str, pl.DataFrame],
    table_max_rows: int = 50,
) -> str:
    environment = TemplateSandbox(undefined=StrictUndefined, autoescape=False)
    environment.globals.clear()
    environment.filters = {
        "upper": lambda value: str(value).upper(),
        "lower": lambda value: str(value).lower(),
        "truncate": lambda value, length=255: str(value)[:length],
        "json": lambda value: json.dumps(value, ensure_ascii=False),
        "table": lambda value: markdown_table(value, table_max_rows),
    }
    try:
        return environment.from_string(source).render(**dict(variables), tables=dict(tables))
    except TemplateError as error:
        line = getattr(error, "lineno", None)
        name = getattr(error, "name", "")
        message = error.message or str(error)
        if not name and message.endswith(" is undefined") and "'" in message:
            name = message.split("'")[1]
        line = line or next(
            (
                number
                for number, text in enumerate(source.splitlines(), 1)
                if name and name in text and "{{" in text
            ),
            None,
        )
        raise ValueError(f"Template line {line or 'unknown'}: {error.message}") from error
