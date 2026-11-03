from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Context:
    root: Path
    run_id: str
    variables: Mapping[str, object]
    log: Callable[[str, str], None]
    progress: Callable[[float, str | None], None]
    cancelled: Callable[[], bool]
    excel: object | None = None
    llm: object | None = None
    stream: Callable[[str], None] | None = None
    usage: Callable[[dict[str, int]], None] | None = None
    node_id: str = ""
    event: Callable[[str, dict[str, Any]], None] | None = None
    node_tool: object | None = None
    session_id: str = ""


_current: ContextVar[Context | None] = ContextVar("weft_context", default=None)


def _get() -> Context:
    context = _current.get()
    if context is None:
        raise RuntimeError("weft_ctx is only available during node execution")
    return context


@contextmanager
def activate(
    root: Path,
    run_id: str,
    variables: Mapping[str, object] | None = None,
    log: Callable[[str, str], None] | None = None,
    progress: Callable[[float, str | None], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    excel: object | None = None,
    llm: object | None = None,
    stream: Callable[[str], None] | None = None,
    usage: Callable[[dict[str, int]], None] | None = None,
    node_id: str = "",
    event: Callable[[str, dict[str, Any]], None] | None = None,
    node_tool: object | None = None,
    session_id: str = "",
) -> Iterator[None]:
    context = Context(
        root=root,
        run_id=run_id,
        variables=MappingProxyType(dict(variables or {})),
        log=log or (lambda level, message: None),
        progress=progress or (lambda fraction, message: None),
        cancelled=cancelled or (lambda: False),
        excel=excel,
        llm=llm,
        stream=stream,
        usage=usage,
        node_id=node_id,
        event=event,
        node_tool=node_tool,
        session_id=session_id,
    )
    token = _current.set(context)
    try:
        yield
    finally:
        _current.reset(token)


def __getattr__(name: str) -> object:
    if name == "root":
        return _get().root
    if name == "run_id":
        return _get().run_id
    if name == "vars":
        return _get().variables
    if name == "node_id":
        return _get().node_id
    if name == "session_id":
        return _get().session_id
    if name == "excel":
        service = _get().excel
        if service is None:
            raise RuntimeError("Excel service is not configured")
        return service
    if name == "llm":
        service = _get().llm
        if service is None:
            raise RuntimeError("LLM service is not configured")
        return service
    if name == "node_tool":
        service = _get().node_tool
        if service is None:
            raise RuntimeError("NodeTool service is not configured")
        return service
    raise AttributeError(name)


def log(message: str, level: str = "INFO") -> None:
    _get().log(level, message)


def progress(fraction: float, msg: str | None = None) -> None:
    if not 0 <= fraction <= 1:
        raise ValueError("Progress must be between 0 and 1")
    _get().progress(fraction, msg)


def stream(delta: str) -> None:
    callback = _get().stream
    if callback is not None:
        callback(delta)


def record_usage(**usage: int) -> None:
    callback = _get().usage
    if callback is not None:
        callback(usage)


def emit_event(event: str, data: dict[str, Any]) -> None:
    callback = _get().event
    if callback is not None:
        callback(event, data)


def check_cancelled() -> None:
    if _get().cancelled():
        raise Cancelled


def resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else _get().root / candidate
