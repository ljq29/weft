from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from weft.api.security import config_dir


class LLMConfigError(ValueError):
    pass


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "config.toml"

    def read(self) -> dict[str, Any]:
        try:
            with self.path.open("rb") as stream:
                return tomllib.load(stream)
        except FileNotFoundError:
            return {}

    def llm(self, name: str) -> dict[str, Any]:
        configs = self.read().get("llm", {})
        if name not in configs:
            raise LLMConfigError(f"LLM config '{name}' not found")
        return dict(configs[name])

    def masked(self) -> dict[str, Any]:
        result = self.read()
        for config in result.get("llm", {}).values():
            if config.get("api_key"):
                config["api_key"] = "***"
        return result

    def update(self, settings: dict[str, Any]) -> dict[str, Any]:
        current = self.read()
        configs = settings.get("llm", {})
        if not isinstance(configs, dict):
            raise LLMConfigError("llm settings must be an object")
        for name, value in configs.items():
            self._validate_llm(name, value, current.get("llm", {}))
        self._write(settings)
        return self.masked()

    def _validate_llm(self, name: str, config: Any, current: dict[str, Any]) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not isinstance(config, dict):
            raise LLMConfigError("Invalid LLM config name or value")
        for field in ("base_url", "model"):
            if not isinstance(config.get(field), str) or not config[field]:
                raise LLMConfigError(f"LLM {field} is required")
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(content, encoding="utf-8")
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
