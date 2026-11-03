import json
import time
from datetime import UTC, datetime
from typing import Any

import simpleeval
from weft_sdk import CachePolicy, Lane, Node, Port

from weft.triggers.chat import ChatSessionStore


class TriggerNode(Node):
    type = "flow.trigger"
    category = "flow"
    name = "Trigger"
    description = "手动、聊天、定时、文件或 HTTP 工作流入口"
    lane = Lane.TRUSTED_SERVICE
    outputs = (
        Port("variable", "variable", "统一触发事件"),
        Port("message", "message", "聊天消息"),
        Port("table", "table", "文件事件表"),
    )
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "manual": {
                "type": "object",
                "description": "手动触发配置",
                "properties": {"enabled": {"type": "boolean", "description": "是否启用手动触发"}},
            },
            "chat": {
                "type": "object",
                "description": "聊天触发配置",
                "properties": {"enabled": {"type": "boolean", "description": "是否启用聊天触发"}},
            },
            "schedule": {
                "type": "object",
                "description": "定时触发配置",
                "properties": {
                    "enabled": {"type": "boolean", "description": "是否启用定时触发"},
                    "schedules": {"type": "array", "description": "cron 或固定间隔列表"},
                },
            },
            "watch": {
                "type": "object",
                "description": "文件监听配置",
                "properties": {
                    "enabled": {"type": "boolean", "description": "是否启用文件监听"},
                    "watches": {"type": "array", "description": "监听路径与规则"},
                },
            },
            "http": {
                "type": "object",
                "description": "HTTP 触发配置",
                "properties": {
                    "enabled": {"type": "boolean", "description": "是否启用 HTTP 触发"},
                    "token_hash": {"type": "string", "description": "工作流令牌哈希"},
                },
            },
        },
    }

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Trigger is executed from its frozen trigger event")


class ChatOutputNode(Node):
    type = "flow.chat_output"
    category = "flow"
    name = "Chat Output"
    description = "将 Message 或 Variable 作为助手消息推送到聊天会话"
    lane = Lane.TRUSTED_SERVICE
    inputs = (Port("message", "message", "消息输入"), Port("variable", "variable", "变量输入"))
    outputs = (Port("message", "message", "助手消息"),)
    params_schema = {
        "type": "object",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {},
    }

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        content: Any = ""
        messages = inputs.get("message", [])
        if messages:
            assistant = next(
                (item for item in reversed(messages) if item.get("role") == "assistant"),
                messages[-1],
            )
            content = assistant.get("content", "")
        elif "variable" in inputs:
            value = inputs["variable"]
            if isinstance(value, dict):
                content = value.get("final_text", value.get("response", value))
            else:
                content = value
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        session_id = ctx.session_id
        message_id = f"m_{ctx.run_id}_{ctx.node_id}"
        record = {
            "session_id": session_id,
            "source_node_id": ctx.node_id,
            "message_id": message_id,
            "role": "assistant",
            "content": content,
            "streaming": False,
            "ts": datetime.now(UTC).isoformat(),
        }
        if session_id:
            ChatSessionStore(ctx.root).append(record)
        ctx.emit_event("chat.message", record)
        return {"message": [{"role": "assistant", "content": content}]}


class HttpResponseNode(Node):
    type = "flow.http_response"
    category = "flow"
    name = "HTTP Response"
    description = "为同步 HTTP 触发提供唯一响应；重复执行会失败"
    lane = Lane.TRUSTED_SERVICE
    inputs = (Port("flow", "flow", "可选执行顺序"),)
    outputs = (Port("response", "variable", "HTTP 响应"),)
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "status_code": {"type": "integer", "description": "HTTP 状态码"},
            "headers": {"type": "object", "description": "响应头"},
            "body": {"description": "文本或 JSON 响应体"},
        },
    }

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        response = {
            "status_code": params.get("status_code", 200),
            "headers": params.get("headers", {}),
            "body": params.get("body", ""),
        }
        ctx.emit_event("http.response", response)
        return {"response": response}


class IfNode(Node):
    type = "flow.if"
    category = "flow"
    name = "If"
    description = "按受限 Python 表达式选择分支"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.PURE
    outputs = (Port("true", "flow", "条件成立"), Port("false", "flow", "条件不成立"))
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"condition": {"type": "string", "description": "变量作用域内的条件表达式"}},
        "required": ["condition"],
    }

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        expression = params["condition"]
        evaluator = simpleeval.SimpleEval(names=dict(ctx.vars), functions={})
        result = evaluator.eval(expression)
        return {"activated_ports": ["true" if result else "false"]}


class SwitchNode(Node):
    type = "flow.switch"
    category = "flow"
    name = "Switch"
    description = "按变量值选择命名分支"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.PURE
    outputs = (
        Port("case_1", "flow", "分支 1"),
        Port("case_2", "flow", "分支 2"),
        Port("case_3", "flow", "分支 3"),
        Port("default", "flow", "默认分支"),
    )
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "variable": {"type": "string", "description": "要匹配的变量名"},
            "cases": {"type": "object", "description": "值到输出端口名的映射"},
        },
        "required": ["variable", "cases"],
    }

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        value = ctx.vars[params["variable"]]
        port = params["cases"].get(str(value), "default")
        if port not in {item.name for item in self.outputs}:
            raise ValueError(f"未知 Switch 输出端口：{port}")
        return {"activated_ports": [port]}


class MergeNode(Node):
    type = "flow.merge"
    category = "flow"
    name = "Merge"
    description = "汇合两个可部分到达的表格分支"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.PURE
    inputs = (Port("left", "table", "左分支"), Port("right", "table", "右分支"))
    outputs = (Port("out", "table", "合并输出"),)

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs.get("left", inputs.get("right"))}


class WaitNode(Node):
    type = "flow.wait"
    category = "flow"
    name = "Wait"
    description = "等待指定秒数并响应取消"
    lane = Lane.TRUSTED_SERVICE
    outputs = (Port("flow", "flow", "等待完成"),)
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "duration_seconds": {
                "type": "number",
                "minimum": 0,
                "description": "等待秒数",
            }
        },
        "required": ["duration_seconds"],
    }

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        deadline = time.monotonic() + params["duration_seconds"]
        while time.monotonic() < deadline:
            ctx.check_cancelled()
            time.sleep(min(0.05, deadline - time.monotonic()))
        return {}


class LoopStartNode(Node):
    type = "flow.loop_start"
    category = "flow"
    name = "Loop Start"
    description = "按行、按块或计数启动循环"
    lane = Lane.TRUSTED_SERVICE
    inputs = (Port("in", "table", "循环输入表"),)
    outputs = (Port("table", "table", "当前行或块"), Port("variables", "variable", "当前迭代变量"))
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["row", "chunk", "counting"],
                "description": "循环模式",
            },
            "loop_id": {"type": "string", "description": "Loop End 配对标识"},
            "chunk_size": {"type": "integer", "minimum": 1, "description": "每块行数"},
            "from": {"type": "integer", "description": "计数起点"},
            "to": {"type": "integer", "description": "计数排他上界"},
            "step": {"type": "integer", "description": "计数步长"},
        },
        "required": ["mode", "loop_id"],
    }

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Loop Start is executed by the loop scheduler")


class LoopEndNode(Node):
    type = "flow.loop_end"
    category = "flow"
    name = "Loop End"
    description = "收集循环体输出"
    lane = Lane.TRUSTED_SERVICE
    inputs = (Port("in", "table", "循环体表格"), Port("variables", "variable", "循环体变量"))
    outputs = (Port("out", "table", "收集后的表格"),)
    params_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "loop_id": {"type": "string", "description": "Loop Start 配对标识"},
            "mode": {
                "type": "string",
                "enum": ["concat", "last", "variables"],
                "description": "收集模式",
            },
            "on_error": {"type": "string", "enum": ["fail", "skip"], "description": "迭代失败策略"},
        },
        "required": ["loop_id", "mode"],
    }

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Loop End is executed by the loop scheduler")
