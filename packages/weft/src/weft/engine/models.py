from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from weft.workflow.models import WorkflowDocument
from weft.workflow.values import ValueRef

RunStatus = Literal["queued", "running", "waiting", "succeeded", "failed", "cancelled"]
NodeStatus = Literal[
    "unconfigured",
    "configured",
    "running",
    "executed",
    "failed",
    "cancelled",
    "out_of_scope",
    "skipped_branch",
    "skipped_upstream",
]


@dataclass
class NodeRecord:
    status: NodeStatus = "configured"
    started_at: str | None = None
    finished_at: str | None = None
    from_cache: bool = False
    error: dict[str, Any] | None = None
    outputs: dict[str, ValueRef] = field(default_factory=dict)
    activated_ports: list[str] | None = None


@dataclass
class RunRecord:
    run_id: str
    workflow_id: str
    workflow_revision: int
    trigger: dict[str, Any]
    scope: dict[str, Any]
    nodes: dict[str, NodeRecord]
    status: RunStatus = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    usage: dict[str, int] = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "llm_calls": 0,
            "tool_calls": 0,
        }
    )
    trace_id: str = ""
    finished: asyncio.Event = field(default_factory=asyncio.Event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id or self.run_id,
            "workflow_id": self.workflow_id,
            "workflow_revision": self.workflow_revision,
            "frozen_workflow": f".runs/{self.run_id}/workflow.json",
            "trigger": self.trigger,
            "scope": self.scope,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "usage": self.usage,
            "nodes": {
                node_id: {
                    "status": record.status,
                    "started_at": record.started_at,
                    "finished_at": record.finished_at,
                    "from_cache": record.from_cache,
                    "error": record.error,
                    "outputs": {
                        port: value.model_dump(mode="json")
                        for port, value in record.outputs.items()
                    },
                    "activated_ports": record.activated_ports,
                }
                for node_id, record in self.nodes.items()
            },
        }


@dataclass
class PreparedRun:
    root: Path
    workflow: WorkflowDocument
    registry: Any
    record: RunRecord
    iteration_index: int | None = None
    chat_links: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    on_finished: Any = None


def now() -> str:
    return datetime.now(UTC).isoformat()
