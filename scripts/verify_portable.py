from __future__ import annotations

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
    environment["PATH"] = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")
    environment["WEFT_CONFIG_DIR"] = str(WORK / "config")
    environment["UV_INDEX_URL"] = "https://pypi.tuna.tsinghua.edu.cn/simple"
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PYTHON", "UV_PROJECT_ENVIRONMENT"):
        environment.pop(name, None)
    return environment


def write_workflow(root: Path) -> None:
    (root / "nodes").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "data" / "input.csv").write_text("amount\n1\n3\n2\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f"""[project]
name = "portable-acceptance"
version = "0.0.0"
requires-python = ">=3.12"
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
            "sourcePort": "out",
            "target": nodes[index][0],
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


def verify_service(executable: Path, environment: dict[str, str]) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [str(executable), "serve", "--no-browser", "--no-triggers", "--port", str(port)],
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
                break
            except (OSError, ValueError):
                time.sleep(0.2)
        else:
            raise AssertionError("Portable service did not become ready")
    finally:
        process.terminate()
        process.wait(timeout=15)


def main() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    executable = BUNDLE / "weft.exe"
    environment = isolated_environment()
    result = subprocess.run(
        [str(executable), "--version"],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stdout.strip() == f"weft {__version__}"
    workflow = WORK / "csv.weft"
    write_workflow(workflow)
    result = subprocess.run(
        [str(executable), "run", str(workflow), "--wait"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (workflow / "out" / "result.csv").read_text(encoding="utf-8-sig").splitlines() == [
        "amount",
        "3",
        "2",
    ]
    verify_service(executable, environment)
    print("Portable CLI, CSV workflow, service API and frontend passed without host Python or uv")


if __name__ == "__main__":
    main()
