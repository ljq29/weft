from __future__ import annotations

import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from weft.agent.settings import SettingsStore
from weft.sandbox.base import SandboxCapabilityError
from weft.sandbox.sandboxie import SandboxieSandbox


def real_sandbox(root: Path, name: str) -> SandboxieSandbox:
    run_id = f"r_{name}_{uuid.uuid4().hex[:8]}"
    start = Path(SettingsStore().read()["sandbox"]["sandboxie"]["start_exe"])
    return SandboxieSandbox(root, run_id, start)


@pytest.mark.win_real
def test_real_sandboxie_read_write_delete_and_unauthorized_path(tmp_path: Path) -> None:
    """US-SBX-03/AC-1..4; US-SBX-04/AC-1: real Sandboxie redirection and deletion audit."""
    root = tmp_path / "workflow"
    root.mkdir()
    source = root / "data.txt"
    source.write_text("real", encoding="utf-8")
    sandbox = real_sandbox(root, "io")
    try:
        assert sandbox.read_file(source) == b"real"
        target = root / "out" / "new.txt"
        sandbox.write_file(target, b"sandboxed")
        assert not target.exists()
        changes = sandbox.collect_changes()
        created = [item for item in changes.changes if item.path == str(target)]
        assert created and created[0].kind == "created"
        assert created[0].source and created[0].source.is_file()
        sandbox.delete_file(source)
        assert source.exists()
        deleted = sandbox.collect_changes()
        assert any(item.path == str(source) and item.kind == "deleted" for item in deleted.changes)
        outside = tmp_path / "outside.txt"
        with pytest.raises(SandboxCapabilityError):
            sandbox.write_file(outside, b"must-not-write")
        assert not outside.exists()
    finally:
        sandbox.discard()


@pytest.mark.win_real
def test_real_sandboxie_network_com_and_owned_box_cleanup(tmp_path: Path) -> None:
    """US-SBX-02/AC-1..4; US-SBX-03/AC-4; US-SBX-06/AC-1: real isolation boundaries."""
    root = tmp_path / "workflow"
    root.mkdir()
    network = real_sandbox(root, "network")
    other = real_sandbox(root, "other")
    network_process = None
    other_process = None
    try:
        network_process = network.spawn(
            [
                sys.executable,
                "-c",
                "import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)",
            ],
            root,
            {},
            15,
        )
        assert network_process.wait(timeout=15) != 0
        com = network.spawn(
            [
                sys.executable,
                "-c",
                "import win32com.client; win32com.client.GetActiveObject('Excel.Application')",
            ],
            root,
            {},
            15,
        )
        assert com.wait(timeout=15) != 0
        other_process = other.spawn(
            [sys.executable, "-c", "import time; time.sleep(30)"], root, {}, 35
        )
        assert other.box != network.box
        assert SandboxieSandbox.cleanup_run(network.run_id)
        assert other.shared_registry_path.exists()
        assert other_process.process.poll() is None
    finally:
        if network_process is not None:
            network_process.close()
        network.discard()
        if other_process is not None:
            other_process.terminate()
            other_process.close()
        other.discard()


@pytest.mark.win_real
def test_real_sandboxie_loopback_proxy_exception(tmp_path: Path) -> None:
    """US-SBX-02/AC-2: the configured loopback LLM proxy remains reachable."""
    root = tmp_path / "workflow"
    root.mkdir()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "5")
            self.end_headers()
            self.wfile.write(b"proxy")

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    sandbox = real_sandbox(root, "loopback")
    process = None
    try:
        process = sandbox.spawn(
            [
                sys.executable,
                "-c",
                "import urllib.request; print("
                f"urllib.request.urlopen('{url}', timeout=5).read().decode())",
            ],
            root,
            {"WEFT_LLM_PROXY_URL": url},
            15,
        )
        assert process.wait(timeout=15) == 0
        assert process.output()[0].strip() == b"proxy"
    finally:
        if process is not None:
            process.close()
        sandbox.discard()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
