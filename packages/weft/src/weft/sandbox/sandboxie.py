from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from weft.agent.settings import SettingsStore
from weft.api.security import config_dir
from weft.sandbox.base import SandboxCapabilityError, SandboxEntry
from weft.sandbox.changes import (
    Change,
    ChangeSet,
    baseline_files,
    file_hash,
    protected_path,
    relative_to_root,
    snapshot_baseline,
)


class SandboxieProcess:
    def __init__(self, process: Any, stdout: Any, stderr: Any, run_id: str) -> None:
        self.process = process
        self.stdout = stdout
        self.stderr = stderr
        self.run_id = run_id
        self.pid = process.pid

    def wait(self, timeout: float | None = None) -> int:
        try:
            return int(self.process.wait(timeout=timeout))
        except subprocess.TimeoutExpired:
            self.terminate()
            raise

    def terminate(self) -> None:
        if self.process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(self.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=10,
            )

    def output(self) -> tuple[bytes, bytes]:
        self.stdout.flush()
        self.stderr.flush()
        return (
            Path(self.stdout.name).read_bytes(),
            Path(self.stderr.name).read_bytes(),
        )

    def close(self) -> None:
        self.stdout.close()
        self.stderr.close()


class SandboxieSandbox:
    def __init__(
        self,
        root: Path,
        run_id: str,
        start_exe: Path,
        sandbox_home: Path | None = None,
        process_factory: Any = subprocess.Popen,
    ) -> None:
        self.root = root.resolve()
        self.run_id = run_id
        self.box = f"WeftBox-{run_id}"
        self.start_exe = start_exe
        self.sandbox_home = sandbox_home or Path("C:/Sandbox")
        self.sandbox_root = self.sandbox_home / os.environ.get("USERNAME", "user") / self.box
        self.process_factory = process_factory
        self.run_dir = self.root / ".runs" / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.run_dir / "sandbox.json"
        self.shared_registry_path = config_dir() / "sandbox-runs" / f"{run_id}.json"
        self.processes: dict[int, SandboxieProcess] = {}
        self.baseline = baseline_files([self.root])
        snapshot_baseline(self.baseline, self.run_dir / "baseline")

    def _record(self) -> dict[str, Any]:
        from weft.excel.xlwings_backend import process_created_at

        return {
            "run_id": self.run_id,
            "box": self.box,
            "root": str(self.root),
            "sandbox_root": str(self.sandbox_root),
            "owned_pids": [
                {
                    "pid": pid,
                    "process_created_at": process_created_at(pid),
                }
                for pid in self.processes
            ],
        }

    def _write_registry(self) -> None:
        content = json.dumps(self._record(), ensure_ascii=False, indent=2)
        self.registry_path.write_text(content, encoding="utf-8")
        self.shared_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.shared_registry_path.write_text(content, encoding="utf-8")

    def spawn(
        self, cmd: list[str], cwd: Path, env: dict[str, str], timeout: float
    ) -> SandboxieProcess:
        allowed_env = {
            key: value
            for key, value in env.items()
            if key in {"WEFT_LLM_PROXY_URL", "WEFT_LLM_CONFIG"}
        }
        process_env = {
            "SystemRoot": os.environ.get("SystemRoot", ""),
            "SystemDrive": os.environ.get("SystemDrive", ""),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONNOUSERSITE": "1",
            **allowed_env,
        }
        identifier = uuid.uuid4().hex
        stdout_path = self.run_dir / f"process-{identifier}.out"
        stderr_path = self.run_dir / f"process-{identifier}.err"
        stdout = stdout_path.open("wb")
        stderr = stderr_path.open("wb")
        command = [
            str(self.start_exe),
            f"/box:{self.box}",
            "/wait",
            "/silent",
            f"/env:WEFT_RUN_ID={self.run_id}",
            *cmd,
        ]
        try:
            process = self.process_factory(
                command,
                cwd=cwd,
                env=process_env,
                stdout=stdout,
                stderr=stderr,
            )
            result = SandboxieProcess(process, stdout, stderr, self.run_id)
            self.processes[result.pid] = result
            self._write_registry()
            return result
        except Exception:
            stdout.close()
            stderr.close()
            raise

    def _helper(self, operation: str, path: Path, *args: str) -> SandboxieProcess:
        target = path if path.is_absolute() else self.root / path
        if not target.resolve().is_relative_to(self.root):
            raise SandboxCapabilityError("Path is outside Root; grant it explicitly first")
        process = self.spawn(
            [sys.executable, "-m", "weft.sandbox.helper", operation, str(target), *args],
            self.root,
            {},
            60,
        )
        if process.wait(timeout=60) != 0:
            _, stderr = process.output()
            raise RuntimeError(stderr.decode("utf-8", errors="replace"))
        return process

    def read_file(self, path: Path) -> bytes:
        process = self._helper("read", path)
        stdout, _ = process.output()
        process.close()
        return stdout

    def write_file(self, path: Path, data: bytes) -> None:
        input_path = self.run_dir / f"write-{uuid.uuid4().hex}.input"
        input_path.write_bytes(data)
        process = self._helper("write", path, "--input", str(input_path))
        process.close()
        input_path.unlink(missing_ok=True)

    def edit_file(self, path: Path, old_string: str, new_string: str) -> None:
        process = self._helper("edit", path, "--old", old_string, "--new", new_string)
        process.close()

    def delete_file(self, path: Path) -> None:
        process = self._helper("delete", path)
        process.close()

    def list_dir(self, path: Path, pattern: str | None = None) -> list[SandboxEntry]:
        process = self._helper("list", path, *(["--pattern", pattern] if pattern else []))
        stdout, _ = process.output()
        process.close()
        return [SandboxEntry(**item) for item in json.loads(stdout)]

    def collect_changes(self) -> ChangeSet:
        changes: list[Change] = []
        warnings: list[str] = []
        drive_root = self.sandbox_root / "drive"
        if drive_root.is_dir():
            for drive in drive_root.iterdir():
                for source in drive.rglob("*"):
                    if not source.is_file():
                        continue
                    target = Path(f"{drive.name}:/") / source.relative_to(drive)
                    baseline_hash = self.baseline.get(target.resolve())
                    current_hash = file_hash(source)
                    if current_hash == baseline_hash:
                        continue
                    data = source.read_bytes()
                    try:
                        is_text = len(data) <= 1024 * 1024 and data.decode("utf-8") is not None
                    except UnicodeDecodeError:
                        is_text = False
                    changes.append(
                        Change(
                            path=str(target),
                            rel_root=relative_to_root(target, self.root),
                            kind="created" if baseline_hash is None else "modified",
                            size=len(data),
                            is_text=is_text,
                            protected=protected_path(target, self.root),
                            baseline_hash=baseline_hash,
                            source=source,
                        )
                    )
        for name in ("user", "temp"):
            if (self.sandbox_root / name).exists():
                warnings.append(f"Unclassified sandbox changes under {name}/")
        from weft.sandbox.review import detect_renames

        result = detect_renames(
            ChangeSet(self.run_id, "sandboxie", changes, not warnings, warnings)
        )
        (self.run_dir / "changes.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result

    def apply(self, changes: list[Change], overwrite_conflicts: bool = False) -> list[Change]:
        raise SandboxCapabilityError("Apply changes through the shared review store")

    def discard(self) -> None:
        self.terminate_owned()
        for change in self.collect_changes().changes:
            if change.state == "pending":
                change.state = "discarded"
        self.collect_changes().audit_warnings.append("Changes discarded")
        shutil.rmtree(self.sandbox_root, ignore_errors=True)
        self.shared_registry_path.unlink(missing_ok=True)

    def terminate_owned(self) -> None:
        if not self.registry_path.exists():
            return
        record = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if record.get("run_id") != self.run_id or record.get("box") != self.box:
            raise SandboxCapabilityError("Sandbox ownership does not match this Run")
        for process in self.processes.values():
            process.terminate()

    @classmethod
    def cleanup_run(cls, run_id: str, settings: SettingsStore | None = None) -> bool:
        path = config_dir() / "sandbox-runs" / f"{run_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return False
        if record.get("run_id") != run_id or not str(record.get("box", "")).endswith(run_id):
            return False
        config = (settings or SettingsStore()).read().get("sandbox", {}).get("sandboxie", {})
        start = config.get("start_exe", r"C:\Program Files\Sandboxie-Plus\Start.exe")
        subprocess.run(
            [start, f"/box:{record['box']}", "/terminate"],
            capture_output=True,
            check=False,
            timeout=30,
        )
        shutil.rmtree(record["sandbox_root"], ignore_errors=True)
        path.unlink(missing_ok=True)
        return True
