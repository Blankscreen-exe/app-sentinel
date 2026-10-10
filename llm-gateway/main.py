"""LLM gateway placeholder (foundation).

A tiny stdlib HTTP server exposing GET /health. No external dependencies so the
image is minimal. In step 3 this is replaced by the real gateway that shells out
to the Claude CLI with built-in tools disabled and validates output against a
JSON schema (ADR-002/003).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path == "/health":
            body = json.dumps({"status": "ok", "role": "llm-gateway-placeholder"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        print(json.dumps({"level": "INFO", "logger": "llm-gateway", "message": fmt % args}))


def main() -> None:
    print(json.dumps({"level": "INFO", "logger": "llm-gateway", "message": "gateway alive :9000"}))
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()


if __name__ == "__main__":
    main()
