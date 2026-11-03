from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def current_process_created_at() -> str:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, kernel32.GetCurrentProcessId())
        if not handle:
            raise ctypes.WinError()
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        try:
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                raise ctypes.WinError()
        finally:
            kernel32.CloseHandle(handle)
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        timestamp = (ticks - 116444736000000000) / 10_000_000
    else:
        boot = next(
            int(line.split()[1])
            for line in Path("/proc/stat").read_text().splitlines()
            if line.startswith("btime ")
        )
        stat = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
        timestamp = boot + int(stat[19]) / os.sysconf("SC_CLK_TCK")
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


class ExecutionLock:
    def __init__(self, root: Path, run_id: str) -> None:
        self.path = root / ".runs" / "engine.lock"
        self.run_id = run_id
        self.stream = None

    @contextmanager
    def acquire(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()
        with self.path.open("r+b") as stream:
            if self.path.stat().st_size == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            stream.seek(0)
            stream.truncate()
            stream.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "process_created_at": current_process_created_at(),
                        "run_id": self.run_id,
                    }
                ).encode()
                + b"\n"
            )
            stream.flush()
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
