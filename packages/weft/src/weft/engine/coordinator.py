from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weft.engine.errors import RunQueueFullError
from weft.engine.models import PreparedRun
from weft.engine.scheduler import Engine
from weft.workflow.models import WorkflowDocument


@dataclass(frozen=True)
class Submission:
    run_id: str | None
    disposition: str


class RunCoordinator:
    def __init__(self, engine: Engine, queue_limit: int = 10, run_retention: int = 50) -> None:
        self.engine = engine
        self.queue_limit = queue_limit
        self.run_retention = run_retention
        self.active: dict[str, str] = {}
        self.queues: dict[str, list[PreparedRun]] = {}
        self.tasks: set[asyncio.Task[Any]] = set()

    async def submit(
        self,
        workflow: WorkflowDocument,
        root: Path,
        registry: Any,
        trigger: dict[str, Any] | None = None,
        scope: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> Submission:
        policy = workflow.settings.concurrency_policy
        if workflow.id in self.active and policy == "drop":
            return Submission(None, "dropped")
        queue = self.queues.setdefault(workflow.id, [])
        if workflow.id in self.active and len(queue) >= self.queue_limit:
            raise RunQueueFullError("RUN_QUEUE_FULL")
        if workflow.id in self.active and policy == "cancel_previous":
            self.engine.cancel(self.active[workflow.id])
        prepared = self.engine.prepare(workflow, root, registry, trigger, scope, trace_id=trace_id)
        prepared.on_finished = self._finished
        if workflow.id in self.active:
            queue.append(prepared)
            return Submission(prepared.record.run_id, "queued")
        self._start(prepared)
        return Submission(prepared.record.run_id, "started")

    def _start(self, prepared: PreparedRun) -> None:
        self.active[prepared.workflow.id] = prepared.record.run_id
        task = asyncio.create_task(self.engine.run(prepared))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _finished(self, prepared: PreparedRun) -> None:
        from weft.workflow.history import RunHistory

        RunHistory(prepared.root).cleanup(self.run_retention)
        self.active.pop(prepared.workflow.id, None)
        queue = self.queues[prepared.workflow.id]
        if queue:
            self._start(queue.pop(0))

    async def wait(self, run_id: str) -> None:
        await self.engine.runs[run_id].record.finished.wait()
