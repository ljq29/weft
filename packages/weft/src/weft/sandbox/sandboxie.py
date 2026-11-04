from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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

SANDBOXIE_DELETED_CTIME = 517247222.25


def sandboxie_box_name(run_id: str, prefix: str = "WeftBox") -> str:
    safe_prefix = re.sub(r"[^A-Za-z0-9_]", "_", prefix)[:12] or "WeftBox"
    safe_run = re.sub(r"[^A-Za-z0-9_]", "_", run_id) or "run"
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:10]
    run_length = 32 - len(safe_prefix) - len(digest) - 2
    return f"{safe_prefix}_{safe_run[:run_length]}_{digest}"


class SandboxieProcess:
    def __init__(
        self,
        process: Any,
        stdout: Any,
        stderr: Any,
        run_id: str,
        sandbox_output: tuple[Path, Path],
        terminate_callback: Callable[[], None],
    ) -> None:
        self.process = process
        self.stdout = stdout
        self.stderr = stderr
        self.run_id = run_id
        self.sandbox_output = sandbox_output
        self.terminate_callback = terminate_callback
        self.pid = process.pid

    def wait(self, timeout: float | None = None) -> int:
        try:
            return int(self.process.wait(timeout=timeout))
        except subprocess.TimeoutExpired:
            self.terminate()
            raise

    def terminate(self) -> None:
        self.terminate_callback()
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
        paths = (
            (self.sandbox_output[0], Path(self.stdout.name)),
            (self.sandbox_output[1], Path(self.stderr.name)),
        )
        return tuple(
            sandboxed.read_bytes() if sandboxed.exists() else original.read_bytes()
            for sandboxed, original in paths
        )  # type: ignore[return-value]

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
        config_runner: Any = subprocess.run,
        box_prefix: str = "WeftBox",
        authorized_roots: list[Path] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.run_id = run_id
        self.box = sandboxie_box_name(run_id, box_prefix)
        self.start_exe = start_exe
        self.sbie_ini = start_exe.with_name("SbieIni.exe")
        self.sandbox_home = sandbox_home or Path("C:/Sandbox")
        self.sandbox_root = self.sandbox_home / os.environ.get("USERNAME", "user") / self.box
        self.process_factory = process_factory
        self.config_runner = config_runner
        self.authorized_roots = [self.root, *(path.resolve() for path in authorized_roots or [])]
        self._box_ready = False
        self.run_dir = self.root / ".runs" / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.run_dir / "sandbox.json"
        self.shared_registry_path = config_dir() / "sandbox-runs" / f"{run_id}.json"
        self.processes: dict[int, SandboxieProcess] = {}
        self.baseline = baseline_files(self.authorized_roots)
        snapshot_baseline(self.baseline, self.run_dir / "baseline")

    def sandboxed_path(self, path: Path) -> Path:
        resolved = path.resolve()
        home = Path.home().resolve()
        if resolved.is_relative_to(home):
            return self.sandbox_root / "user" / "current" / resolved.relative_to(home)
        drive = resolved.drive.rstrip(":\\")
        if not drive:
            raise SandboxCapabilityError(f"Sandbox output requires a local drive path: {path}")
        return self.sandbox_root / "drive" / drive / resolved.relative_to(Path(resolved.anchor))

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

    def _run_ini(self, *args: str) -> None:
        try:
            result = self.config_runner(
                [str(self.sbie_ini), *args],
                capture_output=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exception:
            raise SandboxCapabilityError(f"Cannot configure Sandboxie: {exception}") from exception
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace")
            raise SandboxCapabilityError(f"Sandboxie configuration failed: {message}")

    def _ensure_box(self, env: dict[str, str]) -> None:
        if self._box_ready:
            return
        self._run_ini("set", self.box, "Enabled", "y")
        self._run_ini("set", self.box, "NetworkAccess", "*,Block")
        for root in self.authorized_roots:
            self._run_ini("append", self.box, "NormalFilePath", str(root))
        proxy = env.get("WEFT_LLM_PROXY_URL")
        if proxy:
            parsed = urlsplit(proxy)
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
                raise SandboxCapabilityError("LLM proxy must be a loopback HTTP URL")
            address = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
            port = parsed.port or 80
            self._run_ini(
                "append",
                self.box,
                "NetworkAccess",
                f"*,Allow;Address={address};Port={port};Protocol=TCP",
            )
        self._box_ready = True

    def _box_exists(self) -> bool:
        result = self.config_runner(
            [str(self.sbie_ini), "queryex", "/boxes", "*"],
            capture_output=True,
            check=False,
            timeout=15,
        )
        return self.box in result.stdout.decode("utf-8", errors="replace").splitlines()

    def _terminate_box(self) -> None:
        if not self._box_exists():
            return
        subprocess.run(
            [str(self.start_exe), f"/box:{self.box}", "/terminate"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )

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
            "PYTHONDONTWRITEBYTECODE": "1",
            "WEFT_RUN_ID": self.run_id,
            **allowed_env,
        }
        self._ensure_box(allowed_env)
        identifier = uuid.uuid4().hex
        spec_path = self.run_dir / f"process-{identifier}.json"
        stdout_path = self.run_dir / f"process-{identifier}.out"
        stderr_path = self.run_dir / f"process-{identifier}.err"
        spec_path.write_text(
            json.dumps(
                {"cmd": cmd, "cwd": str(cwd.resolve()), "env": process_env},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        stdout = stdout_path.open("wb")
        stderr = stderr_path.open("wb")
        command = [
            str(self.start_exe),
            f"/box:{self.box}",
            "/wait",
            "/silent",
            f"/env:WEFT_RUN_ID={self.run_id}",
            sys.executable,
            "-m",
            "weft.sandbox.child",
            str(spec_path),
            str(stdout_path),
            str(stderr_path),
        ]
        try:
            process = self.process_factory(
                command,
                cwd=cwd,
                env=process_env,
                stdout=stdout,
                stderr=stderr,
            )
            result = SandboxieProcess(
                process,
                stdout,
                stderr,
                self.run_id,
                (self.sandboxed_path(stdout_path), self.sandboxed_path(stderr_path)),
                self._terminate_box,
            )
            self.processes[result.pid] = result
            self._write_registry()
            return result
        except Exception:
            stdout.close()
            stderr.close()
            raise

    def _helper(self, operation: str, path: Path, *args: str) -> SandboxieProcess:
        target = (path if path.is_absolute() else self.root / path).resolve()
        if not any(target.is_relative_to(root) for root in self.authorized_roots):
            raise SandboxCapabilityError("Path is outside Root; grant it explicitly first")
        for attempt in range(3):
            process = self.spawn(
                [sys.executable, "-m", "weft.sandbox.helper", operation, str(target), *args],
                self.root,
                {},
                60,
            )
            returncode = process.wait(timeout=60)
            if returncode == 0x40010004 and not any(
                path.exists() for path in process.sandbox_output
            ):
                process.close()
                time.sleep(0.2 * (attempt + 1))
                continue
            if returncode != 0:
                _, stderr = process.output()
                message = stderr.decode("utf-8", errors="replace")
                raise RuntimeError(message or f"Sandboxie helper exited with {returncode}")
            return process
        raise RuntimeError("Sandboxie helper could not start after the previous process exited")

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
        locations: list[tuple[Path, Path]] = []
        drive_root = self.sandbox_root / "drive"
        if drive_root.is_dir():
            locations.extend((drive, Path(f"{drive.name}:/")) for drive in drive_root.iterdir())
        user_root = self.sandbox_root / "user" / "current"
        if user_root.is_dir():
            locations.append((user_root, Path.home().resolve()))
        for source_root, target_root in locations:
            for source in source_root.rglob("*"):
                if not source.is_file():
                    continue
                target = target_root / source.relative_to(source_root)
                resolved_target = target.resolve()
                if resolved_target.is_relative_to(self.run_dir):
                    continue
                baseline_hash = self.baseline.get(resolved_target)
                source_stat = source.stat()
                if (
                    baseline_hash is not None
                    and source_stat.st_size == 0
                    and source_stat.st_ctime == SANDBOXIE_DELETED_CTIME
                ):
                    changes.append(
                        Change(
                            path=str(target),
                            rel_root=relative_to_root(target, self.root),
                            kind="deleted",
                            size=0,
                            is_text=False,
                            protected=protected_path(target, self.root),
                            baseline_hash=baseline_hash,
                            source=source,
                        )
                    )
                    continue
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
        unknown_user = self.sandbox_root / "user"
        if unknown_user.is_dir():
            warnings.extend(
                f"Unclassified sandbox changes under user/{item.name}/"
                for item in unknown_user.iterdir()
                if item.name != "current"
            )
        if (self.sandbox_root / "temp").exists():
            warnings.append("Unclassified sandbox changes under temp/")
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
        result = self.collect_changes()
        for change in result.changes:
            if change.state == "pending":
                change.state = "discarded"
        result.audit_warnings.append("Changes discarded")
        (self.run_dir / "changes.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if self._box_ready and self._box_exists():
            self._run_ini("set", self.box, "*", "")
        shutil.rmtree(self.sandbox_root, ignore_errors=True)
        self.shared_registry_path.unlink(missing_ok=True)
        self._box_ready = False

    def terminate_owned(self) -> None:
        if not self.registry_path.exists():
            return
        record = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if record.get("run_id") != self.run_id or record.get("box") != self.box:
            raise SandboxCapabilityError("Sandbox ownership does not match this Run")
        self._terminate_box()

    @classmethod
    def cleanup_run(cls, run_id: str, settings: SettingsStore | None = None) -> bool:
        path = config_dir() / "sandbox-runs" / f"{run_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return False
        config = (settings or SettingsStore()).read().get("sandbox", {}).get("sandboxie", {})
        box = sandboxie_box_name(run_id, config.get("box_prefix", "WeftBox"))
        if record.get("run_id") != run_id or record.get("box") != box:
            return False
        start = Path(config.get("start_exe", r"C:\Program Files\Sandboxie-Plus\Start.exe"))
        ini = start.with_name("SbieIni.exe")
        query = subprocess.run(
            [str(ini), "queryex", "/boxes", "*"], capture_output=True, check=False, timeout=15
        )
        box_exists = box in query.stdout.decode("utf-8", errors="replace").splitlines()
        if query.returncode != 0:
            return False
        if box_exists:
            terminated = subprocess.run(
                [str(start), f"/box:{box}", "/terminate"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
            if terminated.returncode != 0:
                return False
            removed = subprocess.run(
                [str(ini), "set", box, "*", ""],
                capture_output=True,
                check=False,
                timeout=15,
            )
            if removed.returncode != 0:
                return False
        shutil.rmtree(record["sandbox_root"], ignore_errors=True)
        path.unlink(missing_ok=True)
        return True
