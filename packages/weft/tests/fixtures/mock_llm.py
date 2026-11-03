from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class MockLLM:
    def __init__(self) -> None:
        self.scripts: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                mock.requests.append(
                    {"method": "GET", "path": self.path, "headers": dict(self.headers)}
                )
                script = mock._next()
                self._respond(script)

            def do_POST(self) -> None:
                request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                mock.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": request,
                    }
                )
                self._respond(mock._next(), request)

            def _respond(
                self, script: dict[str, Any], request: dict[str, Any] | None = None
            ) -> None:
                status = script.get("status", 200)
                if request and request.get("stream") and status == 200:
                    text = script.get("text", "WEFT_MOCK_OK")
                    chunks = [
                        {
                            "id": "chatcmpl-mock",
                            "object": "chat.completion.chunk",
                            "created": 1,
                            "model": "mock",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"role": "assistant", "content": part},
                                    "finish_reason": None,
                                }
                                for part in script.get("chunks", [text])
                            ],
                        }
                    ]
                    if script.get("tool_calls"):
                        chunks.append(
                            {
                                "id": "chatcmpl-mock",
                                "object": "chat.completion.chunk",
                                "created": 1,
                                "model": "mock",
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"tool_calls": script["tool_calls"]},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                        )
                    chunks.append(
                        {
                            "id": "chatcmpl-mock",
                            "object": "chat.completion.chunk",
                            "created": 1,
                            "model": "mock",
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                            "usage": script.get(
                                "usage", {"prompt_tokens": 3, "completion_tokens": 1}
                            ),
                        }
                    )
                    payload = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
                    payload += "data: [DONE]\n\n"
                    self._write(status, payload, "text/event-stream")
                else:
                    self._write(status, json.dumps(script.get("body", {"error": "mock error"})))

            def _write(
                self, status: int, body: str, content_type: str = "application/json"
            ) -> None:
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler

    def _next(self) -> dict[str, Any]:
        if self.scripts:
            return self.scripts.pop(0)
        return {"body": {"object": "list", "data": [{"id": "mock", "object": "model"}]}}

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self) -> MockLLM:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
