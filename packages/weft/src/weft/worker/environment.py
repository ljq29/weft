from __future__ import annotations

import os
import re
import subprocess
import tomllib
from pathlib import Path

from weft import __version__


class EnvironmentError(RuntimeError):
    pass


class WorkerVersionError(EnvironmentError):
    pass


class WorkflowEnvironment:
    def __init__(self, root: Path, service_version: str = __version__) -> None:
        self.root = root
        self.service_version = service_version

    @property
    def python(self) -> Path:
        if os.name == "nt":
            return self.root / ".venv" / "Scripts" / "python.exe"
        return self.root / ".venv" / "bin" / "python"

    def expected_dependency(self) -> str:
        return f"weft-worker=={self.service_version}"

    def validate_declaration(self) -> None:
        document = tomllib.loads((self.root / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = document.get("project", {}).get("dependencies", [])
        expected = self.expected_dependency()
        if expected not in dependencies:
            actual = next(
                (item for item in dependencies if re.match(r"weft-worker\s*[<>=!~]", item)),
                "missing",
            )
            raise WorkerVersionError(
                f"Worker 版本不一致：需要 {expected}，当前 {actual}；请显式更新、重锁并同步"
            )

    def sync(self) -> None:
        self.validate_declaration()
        if not (self.root / "uv.lock").exists():
            self.run_uv("lock")
        self.run_uv("sync", "--frozen", "--reinstall-package", "weft-worker")
        result = subprocess.run(
            [str(self.python), "-m", "weft_worker.cli", "--version"],
            cwd=self.root,
            capture_output=True,
            text=True,
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        )
        if result.returncode != 0 or result.stdout.strip() != f"weft-worker {self.service_version}":
            raise WorkerVersionError(f"Worker 版本不一致或无法启动：{result.stdout}{result.stderr}")

    def update_worker(self) -> None:
        path = self.root / "pyproject.toml"
        text = path.read_text(encoding="utf-8")
        pattern = r"weft-worker\s*(?:==|>=|<=|~=|!=)\s*[^\"']+"
        replacement = self.expected_dependency()
        updated, count = re.subn(pattern, replacement, text)
        if count == 0:
            raise WorkerVersionError(f"未找到 Worker 依赖，请显式添加 {replacement}")
        path.write_text(updated, encoding="utf-8")
        self.run_uv("lock")
        self.sync()

    def run_uv(self, *args: str) -> None:
        environment = os.environ.copy()
        environment.setdefault("UV_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")
        result = subprocess.run(
            ["uv", *args], cwd=self.root, capture_output=True, text=True, env=environment
        )
        if result.returncode != 0:
            raise EnvironmentError(result.stdout + result.stderr)

    def process_alive(self, pids: list[int]) -> list[int]:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.restype = wintypes.HANDLE
            alive = []
            for pid in pids:
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if not handle:
                    continue
                try:
                    status = wintypes.DWORD()
                    if (
                        kernel32.GetExitCodeProcess(handle, ctypes.byref(status))
                        and status.value == 259
                    ):
                        alive.append(pid)
                finally:
                    kernel32.CloseHandle(handle)
            return alive
        alive = []
        for pid in pids:
            try:
                os.kill(pid, 0)
            except OSError:
                continue
            alive.append(pid)
        return alive
