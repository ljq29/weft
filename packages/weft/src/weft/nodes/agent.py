from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import polars as pl
from weft_sdk import CachePolicy, Lane, Node, Port

from weft.agent.audit import AuditLog, TraceWriter
from weft.agent.loop import run_agent_loop
from weft.agent.settings import SettingsStore
from weft.agent.templates import render_template
from weft.agent.tools import ToolDispatcher
from weft.nodes.excel import schema


def template_inputs(inputs: dict[str, Any]) -> dict[str, pl.DataFrame]:
    return {name: value for name, value in inputs.items() if isinstance(value, pl.DataFrame)}


class PromptTemplateNode(Node):
    type = "agent.prompt_template"
    category = "agent"
    name = "Prompt Template"
    description = "用受限 Jinja2 模板组合变量与只读表格"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.VOLATILE
    inputs = (Port("variables", "variable", "模板变量"), Port("table", "table", "可选表格"))
    outputs = (Port("message", "message", "模板消息"), Port("variable", "variable", "模板文本"))
    params_schema = schema(
        {
            "template": {"type": "string", "description": "Jinja2 模板文本"},
            "source": {"type": "string", "enum": ["inline", "file"], "description": "模板来源"},
            "path": {"type": "string", "description": "prompts/*.md 模板路径"},
            "role": {"type": "string", "enum": ["system", "user"], "description": "消息角色"},
            "table_max_rows": {"type": "integer", "minimum": 0, "description": "表格最大行数"},
        },
        ["template"],
    )
    portable_params = ["path"]

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        source = params["template"]
        if params.get("source") == "file":
            source = ctx.resolve(params["path"]).read_text(encoding="utf-8")
        text = render_template(
            source,
            ctx.vars,
            template_inputs(inputs),
            params.get("table_max_rows", 50),
        )
        role = params.get("role", "user")
        return {"message": [{"role": role, "content": text}], "variable": {"text": text}}


class LLMCallNode(Node):
    type = "agent.llm_call"
    category = "agent"
    name = "LLM Call"
    description = "通过主机 LLMProxy 执行流式文本或 JSON 补全"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.VOLATILE
    inputs = (
        Port("message", "message", "可选历史消息"),
        Port("variables", "variable", "模板变量"),
        Port("table", "table", "可选表格"),
    )
    outputs = (Port("message", "message", "完整消息历史"), Port("variable", "variable", "回复"))
    params_schema = schema(
        {
            "llm": {"type": "string", "description": "命名 LLM 配置"},
            "system_prompt": {"type": "string", "description": "系统提示模板"},
            "user_prompt": {"type": "string", "description": "用户提示模板"},
            "table_max_rows": {"type": "integer", "minimum": 0, "description": "表格最大行数"},
            "temperature": {"type": "number", "description": "采样温度"},
            "max_tokens": {"type": "integer", "minimum": 1, "description": "最大输出 token"},
            "output": {"type": "string", "enum": ["text", "json"], "description": "输出类型"},
            "json_schema": {"type": "object", "description": "可选 JSON Schema"},
        },
        ["llm", "user_prompt"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._execute(ctx, inputs, params))

    async def _execute(
        self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        tables = template_inputs(inputs)
        max_rows = params.get("table_max_rows", 50)
        messages = list(inputs.get("message", []))
        system = render_template(params.get("system_prompt", ""), ctx.vars, tables, max_rows)
        if system:
            messages.append({"role": "system", "content": system})
        user = render_template(params["user_prompt"], ctx.vars, tables, max_rows)
        messages.append({"role": "user", "content": user})
        response_format: dict[str, Any] | None = None
        if params.get("output") == "json":
            response_format = {"type": "json_object"}
            if params.get("json_schema"):
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "weft_response",
                        "schema": params["json_schema"],
                        "strict": True,
                    },
                }
        started = time.perf_counter()
        results = []
        result = await ctx.llm.chat(
            params["llm"],
            messages,
            temperature=params.get("temperature"),
            max_tokens=params.get("max_tokens"),
            response_format=response_format,
            on_text=ctx.stream,
        )
        results.append(result)
        messages.append(result.message)
        response: Any = result.text
        if params.get("output") == "json":
            try:
                response = json.loads(result.text)
            except json.JSONDecodeError:
                messages.append({"role": "user", "content": "请只输出合法 JSON"})
                result = await ctx.llm.chat(
                    params["llm"],
                    messages,
                    temperature=params.get("temperature"),
                    max_tokens=params.get("max_tokens"),
                    response_format=response_format,
                    on_text=ctx.stream,
                )
                results.append(result)
                messages.append(result.message)
                try:
                    response = json.loads(result.text)
                except json.JSONDecodeError as error:
                    raise ValueError(f"LLM JSON parse failed; raw={result.text}") from error
        latency_ms = round((time.perf_counter() - started) * 1000)
        prompt_tokens = sum(item.prompt_tokens for item in results)
        completion_tokens = sum(item.completion_tokens for item in results)
        ctx.record_usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            llm_calls=len(results),
        )
        ctx.log(
            f"prompt_tokens={prompt_tokens} "
            f"completion_tokens={completion_tokens} latency_ms={latency_ms}"
        )
        return {"message": messages, "variable": {"response": response}}


class NodeToolNode(Node):
    type = "agent.node_tool"
    category = "agent"
    name = "Node as Tool"
    description = "把显式授权的节点包装为受控 Agent 工具"
    lane = Lane.TRUSTED_SERVICE
    outputs = (Port("tools", "tool", "授权工具声明"),)
    params_schema = schema(
        {
            "target_node": {"type": "string", "description": "目标节点 ID"},
            "tool_name": {
                "type": "string",
                "pattern": r"^[A-Za-z_][A-Za-z0-9_]*$",
                "description": "工具名",
            },
            "description": {"type": "string", "description": "工具用途"},
            "exposed_params": {"type": "array", "description": "允许模型填写的参数白名单"},
            "result_format": {
                "type": "string",
                "enum": ["table_markdown", "json", "text"],
                "description": "结果格式",
            },
            "allow_side_effects": {"type": "boolean", "description": "显式授权副作用"},
            "require_confirmation": {"type": "boolean", "description": "每次调用需要确认"},
            "tool_timeout": {"type": "number", "minimum": 0.001, "description": "工具超时秒数"},
        },
        ["target_node", "tool_name", "description"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        descriptor = {
            "kind": "node",
            "name": params["tool_name"],
            "description": params["description"],
            "binding": {"target_node": params["target_node"]},
            "exposed_params": params.get("exposed_params", []),
            "result_format": params.get("result_format", "json"),
            "allow_side_effects": params.get("allow_side_effects", False),
            "require_confirmation": params.get("require_confirmation", True),
            "tool_timeout": params.get("tool_timeout", 120),
        }
        return {"tools": descriptor}


class AgentLoopNode(Node):
    type = "agent.loop"
    category = "agent"
    name = "Agent Loop"
    description = "执行可停止、可审计的 ReAct 工具调用循环"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.VOLATILE
    inputs = (
        Port("message", "message", "可选历史消息"),
        Port("variables", "variable", "模板变量"),
        Port("tools", "tool", "授权工具"),
        Port("table", "table", "可选表格"),
    )
    outputs = (
        Port("response", "message", "最终回复"),
        Port("trace", "message", "完整消息轨迹"),
        Port("variable", "variable", "停止原因、轮次和工具统计"),
    )
    params_schema = schema(
        {
            "llm": {"type": "string", "description": "命名 LLM 配置"},
            "system_prompt": {"type": "string", "description": "系统提示模板"},
            "task": {"type": "string", "description": "任务模板"},
            "max_turns": {"type": "integer", "minimum": 1, "description": "最大轮数"},
            "on_max_turns": {
                "type": "string",
                "enum": ["fail", "return_partial"],
                "description": "达到最大轮数时的行为",
            },
            "stop_on_text": {"type": "string", "description": "优先于工具调用的停止正则"},
            "tool_choice": {
                "type": "string",
                "enum": ["auto", "required"],
                "description": "工具选择",
            },
            "tool_timeout": {"type": "number", "minimum": 0.001, "description": "工具超时秒数"},
        },
        ["llm", "task"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._execute(ctx, inputs, params))

    async def _execute(
        self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        raw_tools = inputs.get("tools", [])
        if not isinstance(raw_tools, list):
            raw_tools = [raw_tools]
        tools = [
            tool for item in raw_tools for tool in (item if isinstance(item, list) else [item])
        ]
        tools = [
            ctx.node_tool(tool, ctx.node_id)
            if isinstance(tool, dict) and tool.get("kind") == "node"
            else tool
            for tool in tools
        ]
        dispatcher = ToolDispatcher(
            tools,
            AuditLog(ctx.root, ctx.run_id),
            ctx.node_id,
            params.get("tool_timeout", 120),
            lambda data: ctx.emit_event("node.tool_call", data),
        )
        tables = template_inputs(inputs)
        messages = list(inputs.get("message", []))
        system = render_template(params.get("system_prompt", ""), ctx.vars, tables)
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(
            {"role": "user", "content": render_template(params["task"], ctx.vars, tables)}
        )
        agent_settings = SettingsStore().read().get("agent", {})
        trace = TraceWriter(
            ctx.root,
            ctx.run_id,
            ctx.node_id,
            agent_settings.get("trace_full_prompt", False),
            agent_settings.get("trace_retention_days", 7),
        )
        result = await run_agent_loop(
            llm=ctx.llm,
            config_name=params["llm"],
            messages=messages,
            dispatcher=dispatcher,
            trace=trace,
            max_turns=params.get("max_turns", 20),
            on_max_turns=params.get("on_max_turns", "fail"),
            stop_on_text=params.get("stop_on_text", ""),
            tool_choice=params.get("tool_choice", "auto"),
            on_text=ctx.stream,
            on_turn=lambda data: ctx.emit_event("node.llm_trace", data),
            record_usage=ctx.record_usage,
        )
        if result.partial:
            ctx.log("Agent reached max_turns; returning partial result", level="WARN")
        variable = {
            "final_text": result.final_text,
            "turns": result.turns,
            "tool_calls_count": result.tool_calls_count,
            "stopped_by": result.stopped_by,
            "partial": result.partial,
        }
        return {
            "response": [{"role": "assistant", "content": result.final_text}],
            "trace": result.messages,
            "variable": variable,
        }
