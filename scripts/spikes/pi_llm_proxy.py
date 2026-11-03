"""Verify pi non-interactive mode through a host-side OpenAI-compatible proxy."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class MockLLMHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self.send_json({"object": "list", "data": [{"id": "spike-model", "object": "model"}]})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        auth_ok = self.headers.get("Authorization") == f"Bearer {self.server.expected_key}"
        self.server.requests.append({"auth_ok": auth_ok, "request": request})
        if not auth_ok:
            self.send_error(401)
            return
        chunks = [
            {
                "id": "chatcmpl-spike",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "spike-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "WEFT_PROXY_OK"},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "chatcmpl-spike",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "spike-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            },
        ]
        payload = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        body = payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value: dict[str, Any]) -> None:
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


class LLMProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.endswith("/models"):
            self.forward()
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path.endswith("/chat/completions"):
            self.forward()
        else:
            self.send_error(404)

    def forward(self) -> None:
        parts = self.path.strip("/").split("/")
        if len(parts) < 3 or parts[0] != "v1" or parts[1] not in self.server.llm_configs:
            self.send_error(404)
            return
        config = self.server.llm_configs[parts[1]]
        upstream = urlsplit(config["base_url"])
        if upstream.scheme != "http" or upstream.hostname != "127.0.0.1":
            self.send_error(403)
            return
        connection = http.client.HTTPConnection(upstream.hostname, upstream.port, timeout=30)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "Content-Length": str(length),
        }
        endpoint = "/".join(parts[2:])
        connection.request(self.command, f"{upstream.path}/{endpoint}", body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read()
        self.send_response(response.status)
        self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)
        connection.close()

    def log_message(self, format: str, *args: Any) -> None:
        pass


def start_server(handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".test-reports/pi-spike.json"))
    args = parser.parse_args()
    run_dir = (args.output.parent / f"pi-{uuid.uuid4().hex[:8]}").resolve()
    agent_dir = run_dir / "agent"
    agent_dir.mkdir(parents=True)
    raw_key = f"sk-spike-{uuid.uuid4().hex}"
    mock = start_server(MockLLMHandler)
    mock.expected_key = raw_key
    mock.requests = []
    proxy = start_server(LLMProxyHandler)
    proxy.llm_configs = {
        "default": {
            "base_url": f"http://127.0.0.1:{mock.server_port}/v1",
            "api_key": raw_key,
        }
    }
    host_config = run_dir / "host-config.json"
    host_config.write_text(json.dumps(proxy.llm_configs), encoding="utf-8")
    proxy_url = f"http://127.0.0.1:{proxy.server_port}/v1/default"
    models = {
        "providers": {
            "weft-local": {
                "baseUrl": proxy_url,
                "apiKey": "local-placeholder",
                "authHeader": True,
                "api": "openai-completions",
                "models": [
                    {
                        "id": "spike-model",
                        "name": "Spike Model",
                        "reasoning": False,
                        "input": ["text"],
                        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                        "contextWindow": 128000,
                        "maxTokens": 1024,
                        "compat": {"supportsUsageInStreaming": False},
                    }
                ],
            }
        }
    }
    (agent_dir / "models.json").write_text(json.dumps(models), encoding="utf-8")
    command = [
        shutil.which("pi") or "pi",
        "--provider",
        "weft-local",
        "--model",
        "spike-model",
        "--mode",
        "json",
        "--print",
        "--no-session",
        "--no-tools",
        "--no-extensions",
        "--no-mcp",
        "--no-skills",
        "--no-context-files",
        "Reply with the configured test text only.",
    ]
    env = dict(os.environ)
    env.update(
        {
            "PI_CODING_AGENT_DIR": str(agent_dir),
            "PI_CODING_AGENT_SESSION_DIR": str(run_dir / "sessions"),
            "PI_OFFLINE": "1",
            "PI_TELEMETRY": "0",
        }
    )
    env.pop("OPENAI_API_KEY", None)
    report: dict[str, Any] = {"command": command, "proxy_url": proxy_url}
    try:
        completed = subprocess.run(
            command,
            cwd=run_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        (run_dir / "stdout.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
        child_env_has_key = any(raw_key in value for value in env.values())
        output_has_key = raw_key in completed.stdout or raw_key in completed.stderr
        proxy_passed = (
            completed.returncode == 0
            and "WEFT_PROXY_OK" in completed.stdout
            and bool(mock.requests)
            and all(item["auth_ok"] for item in mock.requests)
            and not child_env_has_key
            and not output_has_key
        )
        report.update(
            {
                "status": "partial",
                "pi_exit_code": completed.returncode,
                "expected_text_received": "WEFT_PROXY_OK" in completed.stdout,
                "upstream_authenticated_by_host_proxy": bool(mock.requests)
                and all(item["auth_ok"] for item in mock.requests),
                "raw_key_in_child_env": child_env_has_key,
                "raw_key_in_stdout_or_stderr": output_has_key,
                "proxy_verified": proxy_passed,
                "sandbox_network_default_deny": "not_verified_sandboxie_missing",
                "run_dir": str(run_dir),
            }
        )
    finally:
        proxy.shutdown()
        mock.shutdown()
        proxy.server_close()
        mock.server_close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    summary = {"status": report.get("status"), "proxy_verified": report.get("proxy_verified")}
    print(json.dumps(summary))
    return 0 if report.get("proxy_verified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
