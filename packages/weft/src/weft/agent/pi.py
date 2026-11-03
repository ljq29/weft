from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from weft.agent.audit import TraceWriter
from weft.agent.proxy import LLMProxy
from weft.agent.proxy_server import LocalLLMProxyServer
from weft.agent.settings import SettingsStore


class PiRunner:
    def __init__(self, root: Path, run_id: str, settings: SettingsStore | None = None) -> None:
        self.root = root
        self.run_id = run_id
        self.settings = settings or SettingsStore()

    def command(self, pi_path: str, model: str, task: str, extra_args: list[str]) -> list[str]:
        return [
            pi_path,
            "--provider",
            "weft-local",
            "--model",
            model,
            "--mode",
            "json",
            "--print",
            "--no-session",
            "--no-tools",
            "--no-extensions",
            "--no-mcp",
            "--no-skills",
            "--no-context-files",
            *extra_args,
            task,
        ]

    def run(
        self,
        *,
        task: str,
        cwd: Path,
        pi_path: str,
        llm: str,
        sandbox: Any,
        timeout: float,
        extra_args: list[str],
        on_event: Any = None,
    ) -> dict[str, Any]:
        executable = pi_path or self.settings.read().get("agent", {}).get("pi_path", "")
        executable = executable or shutil.which("pi") or ""
        if not executable or not Path(executable).is_file():
            raise FileNotFoundError("Pi Agent is not installed; see docs/spikes/pi.md")
        config = self.settings.llm(llm)
        proxy = LocalLLMProxyServer(LLMProxy(self.settings))
        proxy.start()
        agent_dir = self.root / ".runs" / self.run_id / "pi-agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        models = {
            "providers": {
                "weft-local": {
                    "baseUrl": f"{proxy.url}/v1/{llm}",
                    "apiKey": "local-placeholder",
                    "authHeader": True,
                    "api": "openai-completions",
                    "models": [
                        {
                            "id": config["model"],
                            "name": config["model"],
                            "reasoning": False,
                            "input": ["text"],
                            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                            "contextWindow": 128000,
                            "maxTokens": 1024,
                        }
                    ],
                }
            }
        }
        (agent_dir / "models.json").write_text(json.dumps(models), encoding="utf-8")
        process = sandbox.spawn(
            self.command(executable, config["model"], task, extra_args),
            cwd,
            {"WEFT_LLM_PROXY_URL": proxy.url, "WEFT_LLM_CONFIG": llm},
            timeout,
        )
        trace = TraceWriter(self.root, self.run_id, "pi")
        output_path = Path(process.stdout.name)
        offset = 0
        trajectory: list[dict[str, Any]] = []
        final_text = ""
        deadline = time.monotonic() + timeout
        try:
            while True:
                data = output_path.read_bytes() if output_path.exists() else b""
                if len(data) > offset:
                    for line in data[offset:].decode("utf-8", errors="replace").splitlines():
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            event = {"type": "text", "text": line}
                        trajectory.append(event)
                        trace.append(pi_event=event)
                        text = self._event_text(event)
                        if text:
                            final_text = text
                        if on_event is not None:
                            on_event(event)
                    offset = len(data)
                if process.process.poll() is not None:
                    break
                if time.monotonic() >= deadline:
                    process.terminate()
                    raise TimeoutError("Pi Agent timed out")
                time.sleep(0.05)
            exit_code = process.process.wait(timeout=2)
            if exit_code != 0 or self._has_error(trajectory):
                _, stderr = process.output()
                raise RuntimeError(f"Pi Agent failed: {stderr.decode('utf-8', errors='replace')}")
            return {
                "final_text": final_text,
                "exit_code": exit_code,
                "trajectory": trajectory,
            }
        finally:
            process.close()
            proxy.close()

    @staticmethod
    def _event_text(event: dict[str, Any]) -> str:
        if event.get("type") != "message_end":
            return ""
        message = event.get("message", {})
        if message.get("role") != "assistant":
            return ""
        return "".join(
            item.get("text", "")
            for item in message.get("content", [])
            if isinstance(item, dict) and item.get("type") == "text"
        )

    @staticmethod
    def _has_error(events: list[dict[str, Any]]) -> bool:
        def check(value: Any) -> bool:
            if isinstance(value, dict):
                if value.get("stopReason") == "error" or value.get("stop_reason") == "error":
                    return True
                return any(check(item) for item in value.values())
            if isinstance(value, list):
                return any(check(item) for item in value)
            return False

        return check(events)
