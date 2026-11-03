from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from weft.api.security import load_session

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
def test_cli_csv_closed_loop_cache_and_variable_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-EXE-01/AC-1, US-TRG-01/AC-1, US-TRG-02/AC-2: real CLI runs the CSV closed loop."""
    root = tmp_path / "minimal_csv.weft"
    monkeypatch.setenv("WEFT_CONFIG_DIR", str(tmp_path / "config"))
    (root / "nodes").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "data" / "input.csv").write_text("amount\n1\n3\n2\n", encoding="utf-8")
    (root / "data" / "other.csv").write_text("amount\n9\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'''[project]
name = "minimal-csv"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = ["weft-worker==0.0.0"]
[tool.uv.sources]
weft-worker = {{ path = "{(PROJECT_ROOT / "packages/weft-worker").as_posix()}" }}
weft-sdk = {{ path = "{(PROJECT_ROOT / "packages/weft-sdk").as_posix()}" }}
''',
        encoding="utf-8",
    )
    nodes = [
        ("n_00000001", "flow.trigger", {}),
        ("n_00000002", "table.read_csv", {"path": {"$var": "input"}}),
        ("n_00000003", "table.row_filter", {"column": "amount", "operator": ">", "value": "1"}),
        ("n_00000004", "table.sorter", {"keys": [{"column": "amount", "descending": True}]}),
        ("n_00000005", "table.write_csv", {"path": "out/result.csv"}),
    ]
    edges = []
    for index in range(1, len(nodes)):
        edges.append(
            {
                "id": f"e_{index:08x}",
                "source": nodes[index - 1][0],
                "sourcePort": "out" if index > 1 else "variable",
                "target": nodes[index][0],
                "targetPort": "in",
                "order": 0,
            }
        )
    document = {
        "schema_version": 1,
        "revision": 1,
        "id": "wf_0123456789ab",
        "name": "minimal-csv",
        "created_at": "2026-01-01T00:00:00+00:00",
        "modified_at": "2026-01-01T00:00:00+00:00",
        "variables": [{"name": "input", "type": "path", "value": "data/input.csv"}],
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

    def run(*extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "weft", "run", str(root), "--wait", *extra],
            capture_output=True,
            text=True,
            timeout=120,
        )

    first = run()
    assert first.returncode == 0, first.stdout + first.stderr
    assert (root / "out" / "result.csv").read_text(encoding="utf-8-sig").splitlines() == [
        "amount",
        "3",
        "2",
    ]
    second = run()
    assert second.returncode == 0, second.stdout + second.stderr
    runs = sorted(path for path in (root / ".runs").glob("r_*") if path.is_dir())
    latest = json.loads((runs[-1] / "meta.json").read_text(encoding="utf-8"))
    assert latest["nodes"]["n_00000002"]["from_cache"] is True
    assert latest["nodes"]["n_00000003"]["from_cache"] is True
    assert latest["nodes"]["n_00000004"]["from_cache"] is True
    assert latest["nodes"]["n_00000005"]["from_cache"] is False
    overridden = run("--var", "input=data/other.csv")
    assert overridden.returncode == 0, overridden.stdout + overridden.stderr
    assert (root / "out" / "result.csv").read_text(encoding="utf-8-sig").splitlines() == [
        "amount",
        "9",
    ]
    server = subprocess.Popen(
        [sys.executable, "-m", "weft", "serve", "--no-browser"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                request = urllib.request.Request(
                    "http://127.0.0.1:7788/api/system/version",
                    headers={"Authorization": f"Bearer {load_session().token}"},
                )
                with urllib.request.urlopen(request, timeout=0.2) as response:
                    assert json.loads(response.read())["version"] == "0.0.0"
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("Weft service did not start")
        served = run("--var", "input=data/input.csv")
        assert served.returncode == 0, served.stdout + served.stderr
        assert (root / "out" / "result.csv").read_text(encoding="utf-8-sig").splitlines() == [
            "amount",
            "3",
            "2",
        ]
    finally:
        server.terminate()
        server.wait(timeout=10)
