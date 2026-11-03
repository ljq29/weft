import time
from typing import Any

import simpleeval
from weft_sdk import CachePolicy, Lane, Node, Port


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
