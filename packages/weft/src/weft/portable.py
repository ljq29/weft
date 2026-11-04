from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def portable_root() -> Path | None:
    root = Path(sys.executable).resolve().parent
    if (root / "runtime" / "python" / "python.exe").is_file() and (root / "wheels").is_dir():
        return root
    return None


def python_executable() -> Path:
    root = portable_root()
    if root is not None:
        return root / "runtime" / "python" / "python.exe"
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
        environment.setdefault("UV_PYTHON", str(python_executable()))
        environment.setdefault("UV_FIND_LINKS", str(root / "wheels"))
    return environment
