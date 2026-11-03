from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from weft.api.security import config_dir


def configure_service_logging(settings: dict[str, Any]) -> Path:
    config = settings.get("logging", {})
    directory = config_dir() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "weft-{time:YYYY-MM-DD}.log"
    logger.remove()
    logger.configure(
        patcher=lambda record: record["extra"].setdefault(
            "trace_id", record["extra"].get("trace_id", "service")
        )
    )
    logger.add(
        path,
        level=config.get("level", "INFO"),
        serialize=True,
        rotation="00:00",
        retention=f"{config.get('retention_days', 14)} days",
        encoding="utf-8",
    )
    return path


def log_http(method: str, path: str, status: int, trace_id: str) -> None:
    logger.bind(trace_id=trace_id).info("HTTP {} {} -> {}", method, path, status)


def log_excel_call(method: str, run_id: str | None) -> None:
    logger.bind(trace_id=run_id or "excel").debug("Excel COM call summary: {}", method)


def log_llm_request(name: str, method: str, endpoint: str) -> None:
    logger.bind(trace_id=name).debug("LLM request summary: {} {} {}", name, method, endpoint)
