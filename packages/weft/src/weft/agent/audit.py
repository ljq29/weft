from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from weft.engine.models import now
from weft.workflow.values import content_hash

_SENSITIVE = re.compile(r"key|token|password|secret|authorization", re.IGNORECASE)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if _SENSITIVE.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        try:
            url = urlsplit(value)
            if not url.scheme or not url.hostname:
                return value
            host = url.hostname
            auth = "***:***@" if url.username is not None or url.password is not None else ""
            netloc = auth + (host or "")
            if url.port is not None:
                netloc += f":{url.port}"
            query = urlencode(
                [
                    (key, "***" if _SENSITIVE.search(key) else item)
                    for key, item in parse_qsl(url.query, keep_blank_values=True)
                ]
            )
            return urlunsplit((url.scheme, netloc, url.path, query, url.fragment))
        except ValueError:
            return value
    return value


class AuditLog:
    def __init__(self, root: Path, run_id: str) -> None:
        self.path = root / ".runs" / run_id / "audit.jsonl"
        self._lock = threading.Lock()

    def append(
        self,
        *,
        node_id: str,
        tool: str,
        args: Any,
        status: str,
        duration_ms: int,
        result: str,
        agent_kind: str = "agent_loop",
        lane: str = "trusted",
    ) -> dict[str, Any]:
        record = {
            "ts": now(),
            "run_id": self.path.parent.name,
            "node_id": node_id,
            "agent_kind": agent_kind,
            "lane": lane,
            "tool": tool,
            "args_redacted": redact(args),
            "status": status,
            "duration_ms": duration_ms,
            "result_hash": content_hash(result.encode()),
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record


class TraceWriter:
    def __init__(
        self,
        root: Path,
        run_id: str,
        node_id: str,
        include_prompts: bool = False,
        retention_days: int = 7,
    ) -> None:
        if include_prompts and retention_days <= 0:
            raise ValueError("Full-prompt traces require a positive retention period")
        self.path = root / ".runs" / run_id / "nodes" / f"{node_id}.trace.jsonl"
        self.include_prompts = include_prompts
        self._lock = threading.Lock()

    def append(self, **record: Any) -> None:
        record = {"ts": now(), **record}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(redact(record), ensure_ascii=False) + "\n")
