from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Session:
    token: str
    host: str
    port: int
    path: Path


def config_dir() -> Path:
    if override := os.environ.get("WEFT_CONFIG_DIR"):
        return Path(override)
    if appdata := os.environ.get("APPDATA"):
        return Path(appdata) / "weft"
    return Path.home() / ".config" / "weft"


def create_session(host: str, port: int) -> Session:
    path = config_dir() / "session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    session = Session(secrets.token_urlsafe(32), host, port, path)
    path.write_text(
        json.dumps({"token": session.token, "host": host, "port": port}), encoding="utf-8"
    )
    os.chmod(path, 0o600)
    return session


def load_session() -> Session:
    path = config_dir() / "session.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return Session(data["token"], data["host"], data["port"], path)
