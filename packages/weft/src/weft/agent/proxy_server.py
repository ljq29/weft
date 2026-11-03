from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from weft.agent.proxy import LLMProxy


class LocalLLMProxyServer:
    def __init__(self, proxy: LLMProxy) -> None:
        self.proxy = proxy
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        proxy = self.proxy

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self._forward(None)

            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self._forward(json.loads(body))

            def _forward(self, body: Any) -> None:
                parts = self.path.strip("/").split("/")
                if len(parts) < 3 or parts[0] != "v1":
                    self.send_error(404)
                    return
                name, endpoint = parts[1], "/".join(parts[2:])
                if endpoint not in {"models", "chat/completions"}:
                    self.send_error(404)
                    return
                response = asyncio.run(proxy.request(name, self.command, endpoint, body))
                self._write(response.status_code, response.content)

            def _write(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
