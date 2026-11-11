from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_INDEX = PROJECT_ROOT / "packaging" / "bootstrap-index.ps1"
OFFICIAL_INDEX = "https://pypi.org/simple"
TSINGHUA_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"

pytestmark = pytest.mark.integration


def test_bootstrap_script_has_windows_powershell_utf8_bom() -> None:
    """US-SET-04/AC-4: Windows PowerShell 5.1 reads Chinese script text as UTF-8."""
    assert BOOTSTRAP_INDEX.read_bytes().startswith(b"\xef\xbb\xbf")


class IndexHandler(BaseHTTPRequestHandler):
    status_code = 200

    def do_GET(self) -> None:
        self.send_response(self.status_code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


class UnavailableIndexHandler(IndexHandler):
    status_code = 503


def serve_index(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/simple"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def available_index() -> Iterator[str]:
    yield from serve_index(IndexHandler)


@pytest.fixture
def unavailable_index() -> Iterator[str]:
    yield from serve_index(UnavailableIndexHandler)


def run_selector(
    tmp_path: Path,
    choice: str,
    environment_overrides: dict[str, str] | None = None,
) -> tuple[str, str | None, str]:
    selection = tmp_path / "selection.txt"
    insecure_host = tmp_path / "insecure-host.txt"
    environment = os.environ.copy()
    for name in (
        "PIP_INDEX_URL",
        "UV_INDEX_URL",
        "PIP_CONFIG_FILE",
        "WEFT_FORCE_CONFIGURED_INDEX",
    ):
        environment.pop(name, None)
    environment["APPDATA"] = str(tmp_path / "appdata")
    environment["ProgramData"] = str(tmp_path / "program-data")
    environment["USERPROFILE"] = str(tmp_path / "profile")
    if environment_overrides:
        environment.update(environment_overrides)
    system_root = Path(environment.get("SystemRoot", r"C:\Windows"))
    powershell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    result = subprocess.run(
        [
            str(powershell),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BOOTSTRAP_INDEX),
            "-SelectionFile",
            str(selection),
            "-InsecureHostFile",
            str(insecure_host),
            "-ProbeTimeoutSeconds",
            "2",
        ],
        input=f"{choice}\n",
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    return (
        selection.read_text(encoding="utf-8").strip(),
        insecure_host.read_text(encoding="utf-8").strip() if insecure_host.exists() else None,
        output,
    )


def test_bootstrap_uses_reachable_pip_config_index(tmp_path: Path, available_index: str) -> None:
    """US-SET-04/AC-4: bootstrap offers and uses a reachable configured intranet index."""
    config = tmp_path / "pip.ini"
    config.write_text(f"[global]\nindex-url = {available_index}\n", encoding="utf-8")

    selected, insecure_host, output = run_selector(tmp_path, "2", {"PIP_CONFIG_FILE": str(config)})

    assert selected == available_index
    assert insecure_host is not None
    assert insecure_host.startswith("127.0.0.1:")
    assert "2." in output


def test_bootstrap_unavailable_pip_index_reports_reason_and_defaults_to_official(
    tmp_path: Path, unavailable_index: str
) -> None:
    """US-SET-04/AC-4: a failed probe reports its HTTP status and defaults to official."""
    selected, insecure_host, output = run_selector(
        tmp_path, "", {"PIP_INDEX_URL": unavailable_index}
    )

    assert selected == OFFICIAL_INDEX
    assert insecure_host is None
    assert "HTTP 503" in output


def test_bootstrap_menu_can_force_unavailable_pip_index(
    tmp_path: Path, unavailable_index: str
) -> None:
    """US-SET-04/AC-4: menu choice four forces the configured index after a failed probe."""
    selected, insecure_host, output = run_selector(
        tmp_path, "4", {"PIP_INDEX_URL": unavailable_index}
    )

    assert selected == unavailable_index
    assert insecure_host is not None
    assert "HTTP 503" in output


def test_bootstrap_flag_forces_pip_index_without_probe(
    tmp_path: Path, unavailable_index: str
) -> None:
    """US-SET-04/AC-4: the force flag selects the configured index without any probe."""
    selected, insecure_host, output = run_selector(
        tmp_path,
        "",
        {
            "PIP_INDEX_URL": unavailable_index,
            "WEFT_FORCE_CONFIGURED_INDEX": "1",
        },
    )

    assert selected == unavailable_index
    assert insecure_host is not None
    assert "HTTP 503" not in output


@pytest.mark.parametrize(
    ("choice", "expected"),
    [("1", OFFICIAL_INDEX), ("3", TSINGHUA_INDEX)],
)
def test_bootstrap_official_and_tsinghua_choices(
    tmp_path: Path, choice: str, expected: str
) -> None:
    """US-SET-04/AC-4: bootstrap provides explicit official and recommended indexes."""
    selected, insecure_host, _ = run_selector(tmp_path, choice)

    assert selected == expected
    assert insecure_host is None
