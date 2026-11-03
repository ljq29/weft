from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_execution_lock_serializes_two_processes(tmp_path: Path) -> None:
    """US-EXE-13/AC-6: two embedded hosts share one cross-process workflow lock."""
    events = tmp_path / "events.jsonl"
    code = """
import json, sys, time
from pathlib import Path
from weft.engine.lock import ExecutionLock
root = Path(sys.argv[1])
with ExecutionLock(root, "r_lock").acquire():
    now = time.perf_counter()
    with (root / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"start": now}) + "\\n")
    time.sleep(0.2)
    with (root / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"end": time.perf_counter()}) + "\\n")
"""
    processes = [subprocess.Popen([sys.executable, "-c", code, str(tmp_path)]) for _ in range(2)]
    for process in processes:
        assert process.wait(timeout=10) == 0
    rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    intervals = [
        (row["start"], rows[index + 1]["end"]) for index, row in enumerate(rows) if "start" in row
    ]
    assert len(intervals) == 2
    intervals.sort()
    assert intervals[0][1] <= intervals[1][0]
    lock = json.loads((tmp_path / ".runs" / "engine.lock").read_text(encoding="utf-8").strip())
    assert lock["run_id"] == "r_lock"
    assert lock["pid"] > 0
    assert lock["process_created_at"]
