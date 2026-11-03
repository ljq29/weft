from __future__ import annotations

import json
import locale
import os
import re
import subprocess
import threading
import time
from contextvars import copy_context
from typing import Any

from weft_sdk import CachePolicy, Lane, Node, Port
from weft_sdk.context import Cancelled

from weft_worker.builtin import prop, schema

PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def powershell_literal(value: Any) -> str:
    text = text_value(value)
    if "\0" in text:
        raise ValueError("PowerShell 字面量不能包含 NUL")
    return "'" + text.replace("'", "''") + "'"


def cmd_literal(value: Any) -> str:
    text = text_value(value)
    if any(character in text for character in ("\0", '"', "%", "\r", "\n")):
        raise ValueError("cmd 插值不能安全包含双引号、%、换行或 NUL")
    return '"' + text + '"'


def render_command(template: str, variables: dict[str, Any], shell: str) -> str:
    literal = powershell_literal if shell == "powershell" else cmd_literal

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise ValueError(f"Shell 插值变量不存在：{name}")
        return literal(variables[name])

    return PLACEHOLDER.sub(replace, template)


class ShellCommandNode(Node):
    type = "code.shell"
    category = "code"
    name = "Shell Command"
    description = "在可信 Worker 车道执行 PowerShell/cmd，不向 Agent 开放"
    lane = Lane.TRUSTED_WORKER
    cache_policy = CachePolicy.SIDE_EFFECT
    outputs = (Port("variable", "variable", "stdout、stderr 与 exit_code"),)
    params_schema = schema(
        {
            "command": prop("string", "命令；{name} 插值流变量"),
            "cwd": prop("string", "工作目录，默认 Root", default="."),
            "shell": prop("string", "命令解释器", enum=["powershell", "cmd"], default="powershell"),
            "timeout": prop("number", "超时秒数", default=60),
            "env": prop("object", "附加环境变量"),
            "fail_on_nonzero": prop("boolean", "非零退出码时失败", default=True),
        },
        ["command"],
    )

    def execute(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        shell = params.get("shell", "powershell")
        if shell not in {"powershell", "cmd"}:
            raise ValueError("shell 必须为 powershell 或 cmd")
        command = render_command(params["command"], dict(ctx.vars), shell)
        cwd = ctx.resolve(params.get("cwd", "."))
        if not cwd.is_dir():
            raise ValueError(f"Shell 工作目录不存在：{cwd}")
        environment = os.environ.copy()
        extra_env = params.get("env", {})
        if not isinstance(extra_env, dict):
            raise ValueError("env 必须是对象")
        environment.update({str(key): text_value(value) for key, value in extra_env.items()})
        argv = self.argv(command, shell)
        timeout = float(params.get("timeout", 60))
        if timeout <= 0:
            raise ValueError("timeout 必须大于 0")
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="replace",
            bufsize=1,
        )
        stdout: list[str] = []
        stderr: list[str] = []

        def read(stream: Any, target: list[str], level: str) -> None:
            for line in stream:
                text = line.rstrip("\r\n")
                target.append(text)
                ctx.log(text, level=level)

        threads = [
            threading.Thread(
                target=copy_context().run,
                args=(read, process.stdout, stdout, "INFO"),
            ),
            threading.Thread(
                target=copy_context().run,
                args=(read, process.stderr, stderr, "WARN"),
            ),
        ]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                try:
                    ctx.check_cancelled()
                except Cancelled:
                    process.terminate()
                    raise
                if time.monotonic() >= deadline:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise TimeoutError(f"Shell Command 超过 {timeout} 秒")
                time.sleep(0.02)
        finally:
            for thread in threads:
                thread.join(timeout=2)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        exit_code = process.returncode or 0
        if exit_code and params.get("fail_on_nonzero", True):
            raise RuntimeError(f"Shell Command 退出码 {exit_code}：{' '.join(stderr[-5:])}")
        return {
            "variable": {
                "stdout": "\n".join(stdout),
                "stderr": "\n".join(stderr),
                "exit_code": exit_code,
            }
        }

    @staticmethod
    def argv(command: str, shell: str) -> list[str] | str:
        if shell == "powershell":
            executable = "powershell" if os.name == "nt" else "pwsh"
            return [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
        executable = subprocess.list2cmdline([os.environ.get("ComSpec", "cmd.exe")])
        return f"{executable} /d /v:off /c {command}"
