from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from weft import __version__

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(os.environ.get("WEFT_VERIFY_BUNDLE", ROOT / "dist" / "weft-windows-x64"))
WORK = ROOT / ".test-reports" / "portable-acceptance"


def isolated_environment() -> dict[str, str]:
    environment = os.environ.copy()
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    environment["PATH"] = str(system_root / "System32")
    environment["LOCALAPPDATA"] = str(WORK / "local-app-data")
    environment["WEFT_CONFIG_DIR"] = str(WORK / "config")
    environment["PIP_INDEX_URL"] = "https://pypi.tuna.tsinghua.edu.cn/simple"
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "UV_PYTHON",
        "UV_INDEX_URL",
        "PIP_CONFIG_FILE",
        "UV_PROJECT_ENVIRONMENT",
        "UV_FIND_LINKS",
        "UV_CACHE_DIR",
        "UV_PYTHON_INSTALL_DIR",
        "UV_PYTHON_INSTALL_MIRROR",
        "UV_PYTHON_PREFERENCE",
        "UV_PYTHON_DOWNLOADS",
        "UV_OFFLINE",
        "WEFT_PORTABLE_ROOT",
        "WEFT_BASE_PYTHON",
        "WEFT_UV_EXECUTABLE",
    ):
        environment.pop(name, None)
    return environment


def launcher_command(executable: Path, environment: dict[str, str], *args: str) -> list[str]:
    system_root = Path(environment.get("SystemRoot", r"C:\Windows"))
    return [str(system_root / "System32" / "cmd.exe"), "/c", str(executable), *args]


def verify_manifest() -> None:
    manifest = json.loads((BUNDLE / "app" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == __version__
    assert manifest["entrypoint"] == "weft.cmd"
    assert manifest["first_run_download"] is True
    assert (BUNDLE / "bootstrap-index.ps1").read_bytes().startswith(b"\xef\xbb\xbf")
    expected = manifest["files"]
    actual = {
        str(path.relative_to(BUNDLE)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(BUNDLE.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    assert actual == expected
    assert not (BUNDLE / "runtime").exists()
    assert not (BUNDLE / "weft.exe").exists()


def write_workflow(root: Path) -> None:
    (root / "nodes").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "data" / "input.csv").write_text("amount\n1\n3\n2\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f"""[project]
name = "portable-acceptance"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = ["weft-worker=={__version__}"]
""",
        encoding="utf-8",
    )
    nodes = [
        ("n_00000001", "flow.trigger", {}),
        ("n_00000002", "table.read_csv", {"path": "data/input.csv"}),
        ("n_00000003", "table.row_filter", {"column": "amount", "operator": ">", "value": "1"}),
        ("n_00000004", "table.write_csv", {"path": "out/result.csv"}),
    ]
    edges = [
        {
            "id": f"e_{index:08x}",
            "source": nodes[index - 1][0],
            "target": nodes[index][0],
            "sourcePort": "out",
            "targetPort": "in",
            "order": 0,
        }
        for index in range(2, len(nodes))
    ]
    document = {
        "schema_version": 1,
        "revision": 1,
        "id": "wf_0123456789ab",
        "name": "portable-acceptance",
        "created_at": "2026-01-01T00:00:00+00:00",
        "modified_at": "2026-01-01T00:00:00+00:00",
        "variables": [],
        "nodes": [
            {
                "id": node_id,
                "type": node_type,
                "node_version": 1,
                "name": node_type,
                "position": {"x": index * 100, "y": 0},
                "params": params,
            }
            for index, (node_id, node_type, params) in enumerate(nodes)
        ],
        "edges": edges,
    }
    (root / "workflow.json").write_text(json.dumps(document), encoding="utf-8")


def run_workflow(
    executable: Path,
    environment: dict[str, str],
    workflow: Path,
    *options: str,
    input_text: str | None = None,
) -> None:
    result = subprocess.run(
        launcher_command(executable, environment, *options, "run", str(workflow), "--wait"),
        input=input_text,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=360,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (workflow / "out" / "result.csv").read_text(encoding="utf-8-sig").splitlines() == [
        "amount",
        "3",
        "2",
    ]


def stop_process_tree(process: subprocess.Popen[bytes], environment: dict[str, str]) -> None:
    if process.poll() is not None:
        return
    system_root = Path(environment.get("SystemRoot", r"C:\Windows"))
    subprocess.run(
        [
            str(system_root / "System32" / "taskkill.exe"),
            "/PID",
            str(process.pid),
            "/T",
            "/F",
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=15,
    )
    process.wait(timeout=15)


def verify_service(executable: Path, environment: dict[str, str]) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        launcher_command(
            executable,
            environment,
            "--offline",
            "serve",
            "--no-browser",
            "--no-triggers",
            "--port",
            str(port),
        ),
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                token = json.loads((WORK / "config" / "session.json").read_text(encoding="utf-8"))[
                    "token"
                ]
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/system/version",
                    headers={"Authorization": f"Bearer {token}", "X-Weft-Client": "ui"},
                )
                with urllib.request.urlopen(request, timeout=1) as response:
                    assert json.loads(response.read())["version"] == __version__
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                    assert b'<div id="root">' in response.read()
                for asset in ("weft-mark.svg", "weft-logo.svg"):
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/{asset}", timeout=1
                    ) as response:
                        assert response.headers.get_content_type() == "image/svg+xml"
                        assert b"<svg" in response.read()
                break
            except (OSError, ValueError):
                time.sleep(0.2)
        else:
            raise AssertionError("Portable service did not become ready")
    finally:
        stop_process_tree(process, environment)


def main() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    executable = BUNDLE / "weft.cmd"
    environment = isolated_environment()
    verify_manifest()
    result = subprocess.run(
        launcher_command(executable, environment, "--version"),
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stdout.strip() == f"weft {__version__}"
    help_result = subprocess.run(
        launcher_command(executable, environment, "--bootstrap-help"),
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "--china" in help_result.stdout and "--offline" in help_result.stdout
    assert "configured" in help_result.stdout
    assert "--force-configured-index" in help_result.stdout
    workflow = WORK / "csv.weft"
    write_workflow(workflow)
    run_workflow(
        executable,
        environment,
        workflow,
        "--python-mirror",
        "https://gh-proxy.com/https://github.com/astral-sh/python-build-standalone/releases/download",
        input_text="2\n",
    )
    run_workflow(executable, environment, workflow, "--offline")
    run_workflow(executable, environment, workflow, "--offline", "--repair")
    run_workflow(executable, environment, workflow, "--force-configured-index", "--repair")
    run_workflow(executable, environment, workflow, "--offline")
    verify_service(executable, environment)
    print(
        "Portable configured-index bootstrap, forced-index repair, cached offline workflow, "
        "service API and frontend passed without host Python or uv"
    )


if __name__ == "__main__":
    main()
