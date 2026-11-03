from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from weft.workflow.migrations import MigrationRegistry, WorkflowValidationError, load_workflow
from weft.workflow.models import WorkflowDocument


class WorkflowStore:
    def __init__(self, root: Path, migrations: MigrationRegistry | None = None) -> None:
        self.root = root
        self.path = root / "workflow.json"
        self.migrations = migrations or MigrationRegistry()
        self._lock = threading.Lock()

    def load(self) -> WorkflowDocument:
        return load_workflow(self.path, self.migrations)

    def save(
        self,
        document: WorkflowDocument,
        expected_revision: int,
        run_active: bool = False,
    ) -> WorkflowDocument:
        with self._lock:
            current = self.load()
            if current.revision != expected_revision or document.revision != expected_revision:
                raise WorkflowValidationError(
                    f"revision conflict: expected {expected_revision}, current {current.revision}"
                )
            if run_active and current.structural_fingerprint() != document.structural_fingerprint():
                raise WorkflowValidationError("Graph structure cannot change during an active run")
            saved = document.model_copy(
                update={"revision": current.revision + 1, "modified_at": datetime.now(UTC)}
            )
            temporary = self.path.with_name(f"{self.path.name}.tmp")
            temporary.write_text(
                json.dumps(saved.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
            return saved
