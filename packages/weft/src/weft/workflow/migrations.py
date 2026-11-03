from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from weft.workflow.models import CURRENT_SCHEMA_VERSION, WorkflowDocument


class WorkflowValidationError(ValueError):
    pass


Migration = Callable[[dict[str, Any]], dict[str, Any]]


class MigrationRegistry:
    def __init__(self) -> None:
        self._steps: dict[int, Migration] = {}

    def register(self, version: int, migration: Migration) -> None:
        if version < 0 or version in self._steps:
            raise ValueError(f"Invalid or duplicate migration version: {version}")
        self._steps[version] = migration

    def migrate(self, document: dict[str, Any], path: Path) -> dict[str, Any]:
        version = document.get("schema_version")
        if not isinstance(version, int):
            raise WorkflowValidationError("schema_version must be an integer")
        if version > CURRENT_SCHEMA_VERSION:
            raise WorkflowValidationError("工作流版本较新，请升级 Weft")
        original_version = version
        while version < CURRENT_SCHEMA_VERSION:
            migration = self._steps.get(version)
            if migration is None:
                raise WorkflowValidationError(f"Missing migration from schema v{version}")
            if version == original_version:
                backup = path.with_name(f"{path.name}.bak.v{version}")
                backup.write_text(
                    json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            document = migration(document)
            next_version = document.get("schema_version")
            if next_version != version + 1:
                raise WorkflowValidationError(f"Migration v{version} did not increment schema")
            version = next_version
        return document


def load_workflow(path: Path, migrations: MigrationRegistry | None = None) -> WorkflowDocument:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise WorkflowValidationError("workflow.json must contain an object")
    registry = migrations or MigrationRegistry()
    return WorkflowDocument.model_validate(registry.migrate(document, path))
