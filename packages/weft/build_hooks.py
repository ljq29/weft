from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        root = Path(self.root)
        frontend = root.parent.parent / "frontend" / "dist"
        if not (frontend / "index.html").is_file():
            raise RuntimeError("Build frontend/dist before building the Weft wheel")
        target = root / "src" / "weft" / "static"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(frontend, target)
