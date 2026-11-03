from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

RUN_ID = re.compile(r"r_\d{8}_\d{6}_[0-9a-f]{4}")


class RunHistory:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, run_id: str) -> Path:
        if not RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid run_id")
        return self.root / ".runs" / run_id

    def get(self, run_id: str) -> dict[str, Any]:
        value: dict[str, Any] = json.loads(
            (self.path(run_id) / "meta.json").read_text(encoding="utf-8")
        )
        return value

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        records = []
        paths = sorted(
            self.root.glob(".runs/r_*/meta.json"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        for path in paths[: max(0, limit)]:
            data = json.loads(path.read_text(encoding="utf-8"))
            records.append(
                {key: data.get(key) for key in ("run_id", "status", "started_at", "finished_at")}
                | {"trigger_source": data["trigger"]["source"]}
            )
        return records

    def cleanup(self, retention: int = 50) -> list[str]:
        if retention < 0:
            raise ValueError("run_retention must not be negative")
        paths = sorted(
            (path for path in self.root.glob(".runs/r_*") if path.is_dir()),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        deleted = []
        for path in paths[retention:]:
            if not RUN_ID.fullmatch(path.name):
                continue
            shutil.rmtree(path)
            deleted.append(path.name)
        return deleted
