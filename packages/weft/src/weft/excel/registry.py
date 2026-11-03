from __future__ import annotations

import json
import threading
from typing import Any


class RefRegistry:
    def __init__(self) -> None:
        self._objects: dict[str, Any] = {}
        self._runs: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def key(ref: dict[str, Any]) -> str:
        return json.dumps(ref, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def resolve(self, ref: dict[str, Any]) -> Any:
        with self._lock:
            return self._objects.get(self.key(ref), ref)

    def register(self, value: Any, run_id: str | None) -> Any:
        if not isinstance(value, dict) or value.get("kind") not in {"app", "workbook", "range"}:
            return value
        key = self.key(value)
        with self._lock:
            self._objects[key] = value
            if run_id is not None:
                self._runs.setdefault(run_id, set()).add(key)
        return value

    def release_run(self, run_id: str) -> list[Any]:
        with self._lock:
            keys = self._runs.pop(run_id, set())
            return [self._objects.pop(key) for key in keys if key in self._objects]
