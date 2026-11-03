from __future__ import annotations

import importlib
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

if os.name == "nt":
    import ctypes
    from ctypes import wintypes
else:
    fcntl = importlib.import_module("fcntl")


class ExcelGlobalLock:
    def __init__(self) -> None:
        self._stream: BinaryIO | None = None
        self._handle: int | None = None

    @contextmanager
    def acquire(self) -> Iterator[None]:
        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            handle = kernel32.CreateMutexW(None, False, r"Local\WeftExcelCOM")
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = handle
            if kernel32.WaitForSingleObject(handle, 0xFFFFFFFF) != 0:
                kernel32.CloseHandle(handle)
                raise OSError("Cannot acquire Local\\WeftExcelCOM")
            try:
                yield
            finally:
                kernel32.ReleaseMutex(handle)
                kernel32.CloseHandle(handle)
                self._handle = None
        else:
            path = Path(tempfile.gettempdir()) / "weft-excel-com.lock"
            with path.open("a+b") as stream:
                self._stream = stream
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                    self._stream = None
