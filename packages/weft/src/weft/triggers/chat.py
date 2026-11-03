from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from weft.agent.settings import SettingsStore


class ChatDisabledError(ValueError):
    pass


class ChatSessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, session_id: str) -> Path:
        if not re.fullmatch(r"s_[A-Za-z0-9_-]+", session_id):
            raise ValueError("Invalid chat session_id")
        return self.root / ".runs" / "chat" / f"{session_id}.jsonl"

    def append(self, record: dict[str, Any]) -> None:
        session_id = record["session_id"]
        path = self._path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def history(self, session_id: str) -> list[dict[str, Any]]:
        try:
            return [
                json.loads(line)
                for line in self._path(session_id).read_text(encoding="utf-8").splitlines()
                if line
            ]
        except FileNotFoundError:
            return []

    def clear(self, session_id: str, clear_memory: bool = False) -> None:
        self._path(session_id).unlink(missing_ok=True)
        if clear_memory:
            (self.root / ".runs" / "memory" / f"{session_id}.jsonl").unlink(missing_ok=True)

    def cleanup(self) -> None:
        settings = SettingsStore().read().get("cache", {})
        days = settings.get("chat_retention_days", 30)
        if days == 0:
            return
        cutoff = datetime.now(UTC) - timedelta(days=days)
        directory = self.root / ".runs" / "chat"
        for path in directory.glob("s_*.jsonl"):
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff:
                path.unlink()


class ChatSource:
    def __init__(self, coordinator: Any) -> None:
        self.coordinator = coordinator

    async def send(
        self,
        workflow: Any,
        root: Path,
        registry: Any,
        message: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        trigger = next(node for node in workflow.nodes if node.type == "flow.trigger")
        if not trigger.params.get("chat", {}).get("enabled", False):
            raise ChatDisabledError("该工作流未启用聊天触发")
        if not message.strip():
            raise ValueError("聊天内容不能为空")
        session_id = session_id or f"s_{uuid.uuid4().hex}"
        sessions = ChatSessionStore(root)
        sessions.cleanup()
        history_len = len(sessions.history(session_id))
        result = await self.coordinator.submit(
            workflow,
            root,
            registry,
            trigger={
                "source": "chat",
                "ts": datetime.now(UTC).isoformat(),
                "session_id": session_id,
                "payload": {"message": message, "history_len": history_len},
            },
        )
        sessions.append(
            {
                "run_id": result.run_id,
                "session_id": session_id,
                "source_node_id": "chat",
                "message_id": f"m_{uuid.uuid4().hex}",
                "role": "user",
                "content": message,
                "streaming": False,
                "ts": datetime.now(UTC).isoformat(),
            }
        )
        return {
            "run_id": result.run_id,
            "session_id": session_id,
            "disposition": result.disposition,
        }
