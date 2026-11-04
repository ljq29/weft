from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def portable_root() -> Path | None:
    value = os.environ.get("WEFT_PORTABLE_ROOT")
    if value is None:
        return None
    root = Path(value).resolve()
    if (root / "app" / "VERSION").is_file() and (root / "wheels").is_dir():
        return root
    return None


def python_executable() -> Path:
    return Path(sys.executable)


def base_python_executable() -> Path:
    value = os.environ.get("WEFT_BASE_PYTHON")
    if value is not None:
        return Path(value)
    return Path(sys.executable)


def uv_executable() -> str:
    root = portable_root()
    if root is not None:
        return str(root / "tools" / "uv.exe")
    return shutil.which("uv") or "uv"


def uv_environment() -> dict[str, str]:
    environment = os.environ.copy()
    root = portable_root()
    if root is not None:
        environment.setdefault("UV_PYTHON", str(base_python_executable()))
        environment.setdefault("UV_FIND_LINKS", str(root / "wheels"))
        environment.setdefault("UV_PYTHON_PREFERENCE", "only-managed")
        environment.setdefault("UV_PYTHON_DOWNLOADS", "automatic")
        local_app_data = environment.get("LOCALAPPDATA")
        if local_app_data is not None:
            environment.setdefault("UV_CACHE_DIR", str(Path(local_app_data) / "Weft" / "cache"))
            environment.setdefault(
                "UV_PYTHON_INSTALL_DIR", str(Path(local_app_data) / "Weft" / "python")
            )
    return environment
