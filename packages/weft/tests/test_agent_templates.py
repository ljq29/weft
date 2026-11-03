from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from weft.agent.client import LLMClient
from weft.agent.proxy import LLMProxy
from weft.agent.settings import SettingsStore
from weft.agent.templates import render_template
from weft.engine import Engine
from weft.nodes.agent import LLMCallNode, PromptTemplateNode
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument
from weft_sdk import weft_ctx


def test_template_filters_table_limits_and_strict_errors() -> None:
    """US-AGT-02/AC-3; US-AGT-09/AC-1,3,4: safe interpolation and read-only tables."""
    table = pl.DataFrame({"name": ["a|b", "c"], "amount": [1, 2]})
    rendered = render_template(
        "{{ topic | upper }} {% for x in xs %}{{ x }}{% endfor %} {{ tables.in | table }}",
        {"topic": "sales", "xs": [1, 2]},
        {"in": table},
        table_max_rows=1,
    )
    assert "SALES 12" in rendered
    assert "a\\|b" in rendered
    assert "c" not in rendered
    with pytest.raises(ValueError, match=r"line 1.*missing"):
        render_template("{{ missing }}", {}, {})
    with pytest.raises(ValueError, match="__class__"):
        render_template("{{ topic.__class__ }}", {"topic": "sales"}, {})


def test_prompt_template_file_rereads_changes(tmp_path: Path) -> None:
    """US-AGT-09/AC-1,2: file-backed templates render as messages and variables."""
    path = tmp_path / "prompts" / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("Hello {{ name | lower }}", encoding="utf-8")
    with weft_ctx.activate(root=tmp_path, run_id="r_prompt", variables={"name": "WEFT"}):
        params = {"template": "", "source": "file", "path": "prompts/task.md"}
        first = PromptTemplateNode().execute(weft_ctx, {}, params)
        path.write_text("Changed {{ name }}", encoding="utf-8")
        second = PromptTemplateNode().execute(weft_ctx, {}, params)
    assert first["variable"] == {"text": "Hello weft"}
    assert second["message"] == [{"role": "user", "content": "Changed WEFT"}]


def llm_store(tmp_path: Path, mock_llm: Any) -> SettingsStore:
    store = SettingsStore(tmp_path / "config.toml")
    store.update(
        {
            "llm": {
                "default": {
                    "base_url": mock_llm.base_url,
                    "api_key": "not-in-output",
                    "model": "mock-model",
                    "timeout": 3,
                }
            }
        }
    )
    return store


@pytest.mark.integration
def test_llm_call_json_retry_stream_history_and_usage(mock_llm: Any, tmp_path: Path) -> None:
    """US-AGT-02/AC-1..4: templates, JSON retry, stream events and usage work together."""
    store = llm_store(tmp_path, mock_llm)
    mock_llm.scripts.extend(
        [
            {"text": "not-json", "usage": {"prompt_tokens": 3, "completion_tokens": 1}},
            {
                "chunks": ["{", '"category":"报表"}'],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        ]
    )
    deltas: list[str] = []
    usage: dict[str, int] = {}
    with weft_ctx.activate(
        root=tmp_path,
        run_id="r_llm",
        variables={"topic": "销售"},
        llm=LLMClient(LLMProxy(store)),
        stream=deltas.append,
        usage=lambda values: usage.update(values),
    ):
        result = LLMCallNode().execute(
            weft_ctx,
            {
                "table": pl.DataFrame({"note": ["备注"]}),
                "message": [{"role": "user", "content": "old"}],
            },
            {
                "llm": "default",
                "user_prompt": "{{ topic }} {{ tables.table | table }}",
                "output": "json",
                "table_max_rows": 1,
            },
        )
    assert result["variable"] == {"response": {"category": "报表"}}
    assert result["message"][0]["content"] == "old"
    assert "销售" in result["message"][1]["content"]
    assert "备注" in result["message"][1]["content"]
    assert any(item["content"] == "请只输出合法 JSON" for item in result["message"])
    assert deltas == ["not-json", "{", '"category":"报表"}']
    assert usage == {"prompt_tokens": 8, "completion_tokens": 3, "llm_calls": 2}
    assert len(mock_llm.requests) == 2
    assert all(
        request["body"]["response_format"]["type"] == "json_object" for request in mock_llm.requests
    )
    assert "not-in-output" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.integration
def test_llm_call_is_volatile_across_runs(mock_llm: Any, tmp_path: Path) -> None:
    """US-EXE-04/AC-10: identical LLM inputs execute again and return fresh content."""
    store = llm_store(tmp_path, mock_llm)
    mock_llm.scripts.extend([{"text": "first"}, {"text": "second"}])
    document = WorkflowDocument.model_validate(
        {
            "schema_version": 1,
            "revision": 1,
            "id": "wf_aa10000001",
            "name": "llm-volatile",
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "nodes": [
                {
                    "id": "n_00000001",
                    "type": "flow.trigger",
                    "name": "Trigger",
                    "node_version": 1,
                    "position": {"x": 0, "y": 0},
                    "params": {},
                },
                {
                    "id": "n_00000002",
                    "type": "agent.llm_call",
                    "name": "LLM",
                    "node_version": 1,
                    "position": {"x": 0, "y": 0},
                    "params": {"llm": "default", "user_prompt": "ping"},
                },
            ],
            "edges": [],
        }
    )

    async def scenario() -> tuple[Any, Any]:
        engine = Engine(llm_client=LLMClient(LLMProxy(store)))
        registry = builtin_registry()
        first = await engine.run(engine.prepare(document, tmp_path, registry))
        second = await engine.run(engine.prepare(document, tmp_path, registry))
        return first, second

    first, second = asyncio.run(scenario())
    assert first.nodes["n_00000002"].outputs["variable"].inline == {"response": "first"}
    assert second.nodes["n_00000002"].outputs["variable"].inline == {"response": "second"}
    assert second.nodes["n_00000002"].from_cache is False
    assert len(mock_llm.requests) == 2
