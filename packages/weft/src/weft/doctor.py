from __future__ import annotations

import asyncio
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

from weft.agent.settings import SettingsStore
from weft.api.security import config_dir


def _check(checks: list[dict[str, str]], name: str, status: str, message: str) -> None:
    checks.append({"name": name, "status": status, "message": message})


def _cleanup() -> list[str]:
    results = []
    if os.name == "nt":
        from weft.excel.xlwings_backend import OwnedProcessRegistry

        registry = OwnedProcessRegistry()
        for pid in registry.cleanup():
            registry.remove(pid)
            results.append(f"已清理孤儿隐藏 Excel PID {pid}")
    from weft.sandbox.sandboxie import SandboxieSandbox

    for path in config_dir().glob("sandbox-runs/*.json"):
        run_id = path.stem
        try:
            if SandboxieSandbox.cleanup_run(run_id):
                results.append(f"已清理沙箱残留 {run_id}")
        except (OSError, ValueError) as exception:
            results.append(f"沙箱清理失败 {run_id}: {exception}")
    return results


def run_doctor(cleanup: bool = False, settings: SettingsStore | None = None) -> dict[str, Any]:
    store = settings or SettingsStore()
    config = store.read()
    checks: list[dict[str, str]] = []
    python_ok = sys.version_info >= (3, 12)
    _check(checks, "python", "OK" if python_ok else "FAIL", sys.version.split()[0])
    uv = shutil.which("uv")
    _check(checks, "uv", "OK" if uv else "FAIL", uv or "未找到 uv")
    if os.name == "nt":
        try:
            from weft.excel import ExcelWorkerSupervisor

            worker = ExcelWorkerSupervisor(
                backend=config["excel"]["backend"],
                call_timeout=config["excel"]["call_timeout"],
            )
            try:
                instances = asyncio.run(worker.submit("list_instances"))
                _check(
                    checks,
                    "excel",
                    "OK",
                    f"Excel COM 可连接；已打开实例 {len(instances)} 个",
                )
            finally:
                worker.close()
        except Exception as exception:
            _check(checks, "excel", "FAIL", str(exception))
    else:
        _check(checks, "excel", "WARN", "Windows 以外的平台不提供真实 Excel")
    start = Path(config["sandbox"]["sandboxie"]["start_exe"])
    if os.name != "nt":
        _check(checks, "sandboxie", "WARN", "Sandboxie 仅支持 Windows")
    else:
        _check(
            checks,
            "sandboxie",
            "OK" if start.is_file() else "WARN",
            str(start) if start.is_file() else "未安装 Sandboxie；真实沙箱验收不可用",
        )
    configured_pi = config["agent"].get("pi_path", "")
    pi = configured_pi or shutil.which("pi") or ""
    _check(checks, "pi", "OK" if pi else "WARN", str(pi) if pi else "未找到 pi")
    host = config["server"]["host"]
    port = config["server"]["port"]
    try:
        with socket.socket() as sock:
            sock.bind((host, port))
        _check(checks, "port", "OK", f"{host}:{port} 可用")
    except OSError as exception:
        _check(checks, "port", "FAIL", f"{host}:{port} 被占用或不可用：{exception}")
    try:
        directory = config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            probe = Path(stream.name)
        probe.unlink()
        _check(checks, "appdata", "OK", f"{directory} 可写")
    except OSError as exception:
        _check(checks, "appdata", "FAIL", str(exception))
    cleanup_results = _cleanup() if cleanup else []
    failures = sum(item["status"] == "FAIL" for item in checks)
    return {"checks": checks, "cleanup": cleanup_results, "fail_count": failures}
