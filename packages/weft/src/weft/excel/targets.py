from __future__ import annotations

import json
import os
import tomllib
import uuid
from pathlib import Path
from typing import Any


class ExcelTargetStore:
    def __init__(self, path: Path | None = None) -> None:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / ".config"
        self.path = path or base / "weft" / "excel-targets.toml"

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            with self.path.open("rb") as stream:
                return tomllib.load(stream)
        except FileNotFoundError:
            return {}

    def save(self, workflow_id: str, node_id: str, target: dict[str, Any]) -> None:
        allowed = {"workbook", "path", "pid", "window_title"}
        value = {key: target[key] for key in allowed if target.get(key) is not None}
        records = self._read()
        records[f"{workflow_id}.{node_id}"] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = ""
        for key, item in records.items():
            content += f"[{json.dumps(key)}]\n"
            content += "".join(
                f"{field} = {json.dumps(item[field], ensure_ascii=False)}\n"
                for field in sorted(item)
            )
        temporary = self.path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, self.path)

    def get(self, workflow_id: str, node_id: str) -> dict[str, Any]:
        return self._read().get(f"{workflow_id}.{node_id}", {})
