from __future__ import annotations

from pathlib import Path

import pytest
from weft.portable import portable_root, python_executable, uv_environment, uv_executable


def test_portable_paths_use_bundled_python_uv_and_wheels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-SET-04/AC-4: the portable bundle uses its own workflow runtime and dependency sources."""
    root = tmp_path / "bundle"
    python = root / "runtime" / "python" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    (root / "wheels").mkdir()
    (root / "tools").mkdir()
    (root / "tools" / "uv.exe").touch()
    monkeypatch.setattr("weft.portable.sys.executable", str(root / "weft.exe"))
    monkeypatch.delenv("UV_PYTHON", raising=False)
    monkeypatch.delenv("UV_FIND_LINKS", raising=False)

    assert portable_root() == root
    assert python_executable() == python
    assert uv_executable() == str(root / "tools" / "uv.exe")
    environment = uv_environment()
    assert environment["UV_PYTHON"] == str(python)
    assert environment["UV_FIND_LINKS"] == str(root / "wheels")


def test_development_paths_keep_host_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-SET-04/AC-4: a normal source or wheel installation keeps using the host Python."""
    executable = tmp_path / "python.exe"
    monkeypatch.setattr("weft.portable.sys.executable", str(executable))
    monkeypatch.delenv("UV_PYTHON", raising=False)
    monkeypatch.delenv("UV_FIND_LINKS", raising=False)

    assert portable_root() is None
    assert python_executable() == executable
    assert "UV_PYTHON" not in uv_environment()
    assert "UV_FIND_LINKS" not in uv_environment()
