from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from weft.agent.settings import SettingsStore

SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


class MemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, session_id: str) -> Path:
        if not SESSION_ID.fullmatch(session_id):
            raise ValueError("session_id 只能包含字母、数字、下划线和连字符")
        return self.root / ".runs" / "memory" / f"{session_id}.jsonl"

    def load(self, session_id: str, max_messages: int = 20) -> list[dict[str, Any]]:
        if max_messages < 0:
            raise ValueError("max_messages 不能为负数")
        self.cleanup()
        try:
            messages = [
                json.loads(line)
                for line in self.path(session_id).read_text(encoding="utf-8").splitlines()
                if line
            ]
        except FileNotFoundError:
            return []
        return messages[-max_messages:] if max_messages else []

    def save(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        self.cleanup()
        path = self.path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            for message in messages:
                if not isinstance(message, dict) or not isinstance(message.get("role"), str):
                    raise ValueError("Memory 消息必须包含 role")
                stream.write(json.dumps(message, ensure_ascii=False) + "\n")

    def clear(self, session_id: str) -> None:
        self.path(session_id).unlink(missing_ok=True)

    def cleanup(self, retention_days: int | None = None) -> list[Path]:
        days = (
            SettingsStore().read().get("cache", {}).get("memory_retention_days", 30)
            if retention_days is None
            else retention_days
        )
        if days == 0:
            return []
        if days < 0:
            raise ValueError("memory_retention_days 不能为负数")
        cutoff = datetime.now(UTC) - timedelta(days=days)
        deleted = []
        for path in self.root.glob(".runs/memory/*.jsonl"):
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff:
                path.unlink()
                deleted.append(path)
        return deleted
