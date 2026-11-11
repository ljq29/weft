from __future__ import annotations

from pathlib import Path

import pytest
from weft.portable import (
    base_python_executable,
    portable_root,
    python_executable,
    uv_environment,
    uv_executable,
)


def test_portable_paths_use_application_python_managed_base_uv_and_wheels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-SET-04/AC-4: the launcher separates application helpers from the workflow base."""
    root = tmp_path / "bundle"
    (root / "app").mkdir(parents=True)
    (root / "app" / "VERSION").write_text("0.5.2\n", encoding="utf-8")
    (root / "wheels").mkdir()
    (root / "tools").mkdir()
    (root / "tools" / "uv.exe").touch()
    application_python = tmp_path / "app-env" / "Scripts" / "python.exe"
    base_python = tmp_path / "managed" / "python.exe"
    monkeypatch.setattr("weft.portable.sys.executable", str(application_python))
    monkeypatch.setenv("WEFT_PORTABLE_ROOT", str(root))
    monkeypatch.setenv("WEFT_BASE_PYTHON", str(base_python))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("UV_PYTHON", raising=False)
    monkeypatch.delenv("UV_FIND_LINKS", raising=False)
    monkeypatch.delenv("UV_PYTHON_PREFERENCE", raising=False)
    monkeypatch.delenv("UV_PYTHON_DOWNLOADS", raising=False)
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.delenv("UV_PYTHON_INSTALL_DIR", raising=False)

    assert portable_root() == root
    assert python_executable() == application_python
    assert base_python_executable() == base_python
    assert uv_executable() == str(root / "tools" / "uv.exe")
    environment = uv_environment()
    assert environment["UV_PYTHON"] == str(base_python)
    assert environment["UV_FIND_LINKS"] == str(root / "wheels")
    assert environment["UV_PYTHON_PREFERENCE"] == "only-managed"
    assert environment["UV_PYTHON_DOWNLOADS"] == "automatic"
    assert environment["UV_CACHE_DIR"] == str(tmp_path / "local" / "Weft" / "cache")
    assert environment["UV_PYTHON_INSTALL_DIR"] == str(tmp_path / "local" / "Weft" / "python")


def test_development_paths_keep_host_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-SET-04/AC-4: a normal source or wheel installation keeps using the host Python."""
    executable = tmp_path / "python.exe"
    monkeypatch.setattr("weft.portable.sys.executable", str(executable))
    monkeypatch.delenv("WEFT_PORTABLE_ROOT", raising=False)
    monkeypatch.delenv("WEFT_BASE_PYTHON", raising=False)
    monkeypatch.delenv("UV_PYTHON", raising=False)
    monkeypatch.delenv("UV_FIND_LINKS", raising=False)

    assert portable_root() is None
    assert python_executable() == executable
    assert base_python_executable() == executable
    assert "UV_PYTHON" not in uv_environment()
    assert "UV_FIND_LINKS" not in uv_environment()
