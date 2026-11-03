from __future__ import annotations

from typing import Any

from weft_sdk import CachePolicy, Lane, Node, Port

from weft.agent.memory import MemoryStore
from weft.nodes.excel import schema


def session_id(ctx: Any, params: dict[str, Any]) -> str:
    value = params.get("session_id") or ctx.session_id
    if not isinstance(value, str) or not value:
        raise ValueError("Memory 节点需要 session_id")
    return value


class MemoryLoadNode(Node):
    type = "agent.memory_load"
    category = "agent"
    name = "Memory Load"
    description = "读取指定会话的最新消息，不跨 Run 缓存"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.VOLATILE
    inputs = (Port("message", "message", "可选执行顺序"),)
    outputs = (Port("message", "message", "会话消息"),)
    params_schema = schema(
        {
            "session_id": {"type": "string", "description": "会话 ID；空值使用聊天会话"},
            "max_messages": {
                "type": "integer",
                "minimum": 0,
                "default": 20,
                "description": "最多保留的最新消息数",
            },
        },
        ["session_id"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        messages = MemoryStore(ctx.root).load(
            session_id(ctx, params), params.get("max_messages", 20)
        )
        return {"message": messages}


class MemorySaveNode(Node):
    type = "agent.memory_save"
    category = "agent"
    name = "Memory Save"
    description = "向指定会话追加 Message 输入"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.SIDE_EFFECT
    inputs = (Port("message", "message", "要追加的消息"),)
    outputs = (Port("message", "message", "已保存消息"),)
    params_schema = schema(
        {"session_id": {"type": "string", "description": "会话 ID；空值使用聊天会话"}},
        ["session_id"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        raw = inputs.get("message", [])
        messages = raw if isinstance(raw, list) else [raw]
        MemoryStore(ctx.root).save(session_id(ctx, params), messages)
        return {"message": messages}


class MemoryClearNode(Node):
    type = "agent.memory_clear"
    category = "agent"
    name = "Memory Clear"
    description = "清空指定会话的 Memory 数据"
    lane = Lane.TRUSTED_SERVICE
    cache_policy = CachePolicy.SIDE_EFFECT
    inputs = (Port("message", "message", "可选执行顺序"),)
    outputs = (Port("variable", "variable", "清理结果"),)
    params_schema = schema(
        {"session_id": {"type": "string", "description": "会话 ID；空值使用聊天会话"}},
        ["session_id"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        selected = session_id(ctx, params)
        MemoryStore(ctx.root).clear(selected)
        return {"variable": {"cleared": True, "session_id": selected}}
