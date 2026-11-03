from __future__ import annotations

import asyncio
import fnmatch
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def validate_trigger_config(workflow: Any) -> None:
    trigger = next(node for node in workflow.nodes if node.type == "flow.trigger")
    for item in trigger.params.get("schedule", {}).get("schedules", []):
        if item.get("cron"):
            CronTrigger.from_crontab(item["cron"])
        elif float(item.get("interval_seconds", 0)) <= 0:
            raise ValueError("interval_seconds must be positive")


class _WatchHandler(FileSystemEventHandler):
    def __init__(self, manager: TriggerManager, workflow_id: str, config: dict[str, Any]) -> None:
        self.manager = manager
        self.workflow_id = workflow_id
        self.config = config
        self.events: dict[str, dict[str, Any]] = {}
        self.timer: asyncio.TimerHandle | None = None

    def on_any_event(self, event: Any) -> None:
        path = Path(str(event.src_path)).resolve()
        kind = str(event.event_type)
        if kind not in self.config.get("events", ["created", "modified", "deleted"]):
            return
        if not fnmatch.fnmatch(path.name, self.config.get("pattern", "*")):
            return
        if path.name.startswith(("~$", ".~lock")) or path.suffix == ".tmp":
            return
        if self.manager.suppressed(path):
            return
        root = Path(self.config["resolved_path"]).resolve()
        if path.is_relative_to(root) and path.relative_to(root).parts:
            if path.relative_to(root).parts[0] in {".runs", ".venv"}:
                return
        self.events[str(path)] = {
            "path": str(path),
            "kind": kind,
            "ts": datetime.now(UTC).isoformat(),
        }
        delay = self.config.get("debounce_ms", 2000) / 1000
        if self.timer is not None:
            self.timer.cancel()
        loop = self.manager.loop
        if loop is None:
            return
        self.timer = loop.call_later(delay, self.flush)

    def flush(self) -> None:
        events = list(self.events.values())
        self.events.clear()
        self.timer = None
        if events:
            asyncio.create_task(self.manager.emit(self.workflow_id, "file", {"events": events}))


class TriggerManager:
    def __init__(self, coordinator: Any, roots: dict[str, Path]) -> None:
        self.coordinator = coordinator
        self.roots = roots
        self.scheduler = AsyncIOScheduler()
        self.observers: dict[str, list[Any]] = {}
        self.health: dict[str, dict[str, Any]] = {}
        self.suppressions: dict[Path, float] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def activate(self, workflow: Any, root: Path) -> None:
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        self.roots[workflow.id] = root
        self.deactivate(workflow.id)
        trigger = next(node for node in workflow.nodes if node.type == "flow.trigger")
        params = trigger.params
        health: dict[str, Any] = {
            source: {
                "enabled": bool(params.get(source, {}).get("enabled", False)),
                "status": "ok" if params.get(source, {}).get("enabled", False) else "disabled",
            }
            for source in ("manual", "chat", "schedule", "watch", "http")
        }
        schedule = params.get("schedule", {})
        if schedule.get("enabled"):
            if not self.scheduler.running:
                self.scheduler.start()
            health["schedule"] = {"enabled": True, "status": "ok", "next": []}
            for index, item in enumerate(schedule.get("schedules", [])):
                if item.get("cron"):
                    parsed = CronTrigger.from_crontab(item["cron"])
                else:
                    seconds = float(item["interval_seconds"])
                    if seconds <= 0:
                        raise ValueError("interval_seconds must be positive")
                    parsed = IntervalTrigger(seconds=seconds)
                schedule_id = f"{workflow.id}:{index}:{uuid.uuid4().hex[:6]}"
                self.scheduler.add_job(
                    self._schedule_job,
                    parsed,
                    args=[workflow.id, schedule_id],
                    id=schedule_id,
                    replace_existing=True,
                    coalesce=False,
                )
                next_run = parsed.get_next_fire_time(None, datetime.now(UTC))
                health["schedule"]["next"].append(
                    {
                        "schedule_id": schedule_id,
                        "next_at": next_run.isoformat() if next_run else None,
                    }
                )
        watches = params.get("watch", {})
        if watches.get("enabled"):
            health["watch"] = {"enabled": True, "status": "ok", "paths": []}
            for item in watches.get("watches", []):
                path = Path(item["path"])
                path = path if path.is_absolute() else root / path
                if not path.is_dir():
                    health["watch"]["paths"].append({"path": str(path), "status": "error"})
                    continue
                config = dict(item)
                config["resolved_path"] = str(path)
                observer = Observer()
                handler = _WatchHandler(self, workflow.id, config)
                observer.schedule(handler, str(path), recursive=item.get("recursive", False))
                observer.start()
                self.observers.setdefault(workflow.id, []).append(observer)
                health["watch"]["paths"].append({"path": str(path), "status": "ok"})
            if any(item["status"] == "error" for item in health["watch"]["paths"]):
                health["watch"]["status"] = "error"
        self.health[workflow.id] = health

    def _schedule_job(self, workflow_id: str, schedule_id: str) -> None:
        if self.loop is None or self.loop.is_closed():
            return

        def submit() -> None:
            asyncio.create_task(
                self.emit(
                    workflow_id,
                    "schedule",
                    {
                        "schedule_id": schedule_id,
                        "scheduled_at": datetime.now(UTC).isoformat(),
                    },
                )
            )

        self.loop.call_soon_threadsafe(submit)

    async def emit(self, workflow_id: str, source: str, payload: dict[str, Any]) -> Any:
        from weft.triggers.preflight import precheck_excel_targets
        from weft.workflow import WorkflowStore

        root = self.roots[workflow_id]
        workflow = WorkflowStore(root).load()
        await precheck_excel_targets(workflow, self.coordinator.engine)
        return await self.coordinator.submit(
            workflow,
            root,
            self.coordinator.engine.registry
            if hasattr(self.coordinator.engine, "registry")
            else self.registry,
            trigger={
                "source": source,
                "ts": datetime.now(UTC).isoformat(),
                "payload": payload,
            },
        )

    @property
    def registry(self) -> Any:
        from weft.nodes.registry import builtin_registry

        return builtin_registry()

    def suppress(self, path: Path, ttl: float = 4) -> None:
        if self.loop is not None:
            self.suppressions[path.resolve()] = self.loop.time() + ttl

    def suppressed(self, path: Path) -> bool:
        if self.loop is None:
            return False
        expiry = self.suppressions.get(path.resolve(), 0)
        if expiry < self.loop.time():
            self.suppressions.pop(path.resolve(), None)
            return False
        return True

    def deactivate(self, workflow_id: str) -> None:
        for job in list(self.scheduler.get_jobs()):
            if job.id.startswith(f"{workflow_id}:"):
                job.remove()
        for observer in self.observers.pop(workflow_id, []):
            observer.stop()
            observer.join(timeout=2)
        self.health.pop(workflow_id, None)

    def close(self) -> None:
        for workflow_id in list(self.observers):
            self.deactivate(workflow_id)
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
