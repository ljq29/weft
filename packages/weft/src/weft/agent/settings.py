from __future__ import annotations

import copy
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from weft.api.security import config_dir

DEFAULT_SETTINGS: dict[str, Any] = {
    "server": {
        "host": "127.0.0.1",
        "port": 7788,
        "open_browser": True,
        "global_token": "",
    },
    "sandbox": {
        "default": "sandboxie",
        "allow_none_sandbox": False,
        "network": "deny",
        "authorized_roots": [],
        "sandboxie": {
            "start_exe": r"C:\Program Files\Sandboxie-Plus\Start.exe",
            "box_prefix": "WeftBox",
        },
    },
    "excel": {"backend": "xlwings", "call_timeout": 60, "restart_after_timeouts": 3},
    "agent": {
        "pi_path": "",
        "confirm_timeout_s": 600,
        "trace_full_prompt": False,
        "trace_retention_days": 7,
    },
    "trigger": {"http_wait_timeout_s": 300},
    "logging": {"level": "INFO", "retention_days": 14},
    "cache": {
        "max_mb": 2048,
        "run_retention": 50,
        "chat_retention_days": 30,
        "memory_retention_days": 30,
    },
}


class LLMConfigError(ValueError):
    pass


def merge_settings(current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(current)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "config.toml"

    def ensure(self) -> None:
        if not self.path.exists():
            self._write(DEFAULT_SETTINGS)

    def read(self) -> dict[str, Any]:
        self.ensure()
        try:
            with self.path.open("rb") as stream:
                stored = tomllib.load(stream)
        except tomllib.TOMLDecodeError as exception:
            raise LLMConfigError(f"配置 TOML 解析失败：{exception}") from exception
        result = merge_settings(DEFAULT_SETTINGS, stored)
        self._validate(result)
        return result

    def llm(self, name: str) -> dict[str, Any]:
        configs = self.read().get("llm", {})
        if name not in configs:
            raise LLMConfigError(f"LLM config '{name}' not found")
        return dict(configs[name])

    def llm_draft(self, name: str, config: dict[str, Any]) -> dict[str, Any]:
        draft = copy.deepcopy(config)
        self._validate_llm(name, draft, self.read().get("llm", {}), require_model=False)
        return draft

    def masked(self) -> dict[str, Any]:
        result = copy.deepcopy(self.read())
        for config in result.get("llm", {}).values():
            if config.get("api_key"):
                config["api_key"] = "***"
        return result

    def update(self, settings: dict[str, Any]) -> dict[str, Any]:
        current = self.read()
        updates = copy.deepcopy(settings)
        configs = updates.get("llm", {})
        if not isinstance(configs, dict):
            raise LLMConfigError("llm settings must be an object")
        for name, value in configs.items():
            self._validate_llm(name, value, current.get("llm", {}))
        merged = merge_settings(current, updates)
        if "llm" in updates:
            merged["llm"] = configs
        self._validate(merged)
        self._write(merged)
        return self.masked()

    def _validate(self, settings: dict[str, Any]) -> None:
        def known(value: dict[str, Any], defaults: dict[str, Any], prefix: str) -> None:
            for key, item in value.items():
                path = f"{prefix}.{key}" if prefix else key
                if not prefix and key == "llm":
                    if not isinstance(item, dict):
                        raise LLMConfigError("配置字段 llm 必须是对象")
                    continue
                if key not in defaults:
                    if prefix == "llm":
                        continue
                    raise LLMConfigError(f"未知配置字段：{path}")
                expected = defaults[key]
                if isinstance(expected, dict) and not isinstance(item, dict):
                    raise LLMConfigError(f"配置字段 {path} 必须是对象")
                if expected is not None and not isinstance(expected, dict):
                    if isinstance(expected, bool):
                        valid = isinstance(item, bool)
                    elif isinstance(expected, (int, float)):
                        valid = isinstance(item, (int, float)) and not isinstance(item, bool)
                    else:
                        valid = isinstance(item, type(expected))
                    if not valid:
                        raise LLMConfigError(f"配置字段 {path} 类型错误")

        known(settings, DEFAULT_SETTINGS, "")
        for name, config in settings.get("llm", {}).items():
            self._validate_llm(name, config, settings.get("llm", {}))
        ranges = {
            "server.port": (1, 65535),
            "excel.call_timeout": (0.001, 600),
            "excel.restart_after_timeouts": (1, 100),
            "agent.confirm_timeout_s": (0.001, 86400),
            "agent.trace_retention_days": (0, 3650),
            "trigger.http_wait_timeout_s": (0.001, 3600),
            "logging.retention_days": (0, 3650),
            "cache.max_mb": (1, 1024 * 1024),
            "cache.run_retention": (0, 100000),
            "cache.chat_retention_days": (0, 3650),
            "cache.memory_retention_days": (0, 3650),
        }
        for path, (minimum, maximum) in ranges.items():
            section, key = path.rsplit(".", 1)
            value = settings[section][key]
            if not minimum <= value <= maximum:
                raise LLMConfigError(f"配置字段 {path} 必须在 {minimum}..{maximum} 之间")
        if settings["sandbox"]["default"] not in {"sandboxie", "none"}:
            raise LLMConfigError("配置字段 sandbox.default 必须是 sandboxie 或 none")
        if settings["logging"]["level"] not in {"DEBUG", "INFO", "WARN", "ERROR"}:
            raise LLMConfigError("配置字段 logging.level 无效")

    def _validate_llm(
        self, name: str, config: Any, current: dict[str, Any], require_model: bool = True
    ) -> None:
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
            or not isinstance(config, dict)
        ):
            raise LLMConfigError("Invalid LLM config name or value")
        fields = ("base_url", "model") if require_model else ("base_url",)
        for field in fields:
            if not isinstance(config.get(field), str) or not config[field]:
                raise LLMConfigError(f"LLM {name}.{field} is required")
        if "model" in config and not isinstance(config["model"], str):
            raise LLMConfigError(f"LLM {name}.model must be a string")
        url = urlsplit(config["base_url"])
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise LLMConfigError("LLM base_url must be an HTTP(S) URL without userinfo")
        timeout = config.get("timeout", 120)
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 600:
            raise LLMConfigError("LLM timeout must be between 0 and 600 seconds")
        headers = config.get("extra_headers", {})
        if not isinstance(headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
        ):
            raise LLMConfigError("extra_headers must contain string values")
        api_key = config.get("api_key", "")
        if not isinstance(api_key, str):
            raise LLMConfigError("api_key must be a string")
        if api_key == "***":
            config["api_key"] = current.get(name, {}).get("api_key", "")

    def _write(self, settings: dict[str, Any]) -> None:
        content = self._sections(settings)
        header = (
            "# Weft user settings\n"
            "# Add named LLM sections such as [llm.default].\n"
            "# API keys stay in this user-level file and are never packed.\n"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(header + content, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    def _sections(self, value: dict[str, Any], prefix: str = "") -> str:
        lines = []
        for key, item in sorted(value.items(), key=lambda pair: isinstance(pair[1], dict)):
            key_text = key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if isinstance(item, dict):
                lines.extend(["", f"[{path}]", self._sections(item, path)])
            else:
                lines.append(f"{json.dumps(key)} = {self._toml(item)}")
        return "\n".join(lines).lstrip() + "\n"

    def _toml(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (str, int, float)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, list):
            return "[" + ", ".join(self._toml(item) for item in value) + "]"
        raise LLMConfigError(f"Unsupported settings value: {type(value).__name__}")
