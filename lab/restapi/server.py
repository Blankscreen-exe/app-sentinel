"""Mock generic REST API for the lab.

Demonstrates the generic unauthenticated-endpoint check. Synthetic data only.

Endpoints:
  GET /api/orders   broken: 200 + data (missing auth)  ·  correct: 401 unauthorized
  GET /health       200 {"status":"ok"} in BOTH modes  (legitimately public)
  GET /             200 html in BOTH modes              (marketing page)
  POST /__mode/<broken|correct>   lab-only control

The /health and / endpoints exist on purpose: a generic REST probe cannot *know* whether
a 200 is meant to be public, so the check must report such hits as CANDIDATES for human
review — never as confirmed vulnerabilities.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

_ORDERS = [{"id": 1, "customer": "Wayne LLC", "total": 1999.0},
           {"id": 2, "customer": "Stark Inc", "total": 499.0}]
_mode = {"value": "broken"}


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: object) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _html(self, code: int, body: str) -> None:
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/__mode/"):
            m = self.path.rsplit("/", 1)[-1]
            if m in ("broken", "correct"):
                _mode["value"] = m
                self._json(200, {"mode": m})
            else:
                self._json(400, {"error": "bad mode"})
            return
        self._json(404, {"error": "not found"})

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/__mode":
            self._json(200, {"mode": _mode["value"]})
        elif route == "/health":
            self._json(200, {"status": "ok"})
        elif route == "/":
            self._html(200, "<html><body>Acme API</body></html>")
        elif route == "/api/orders":
            if _mode["value"] == "correct":
                self._json(401, {"error": "unauthorized"})
            else:
                self._json(200, _ORDERS)  # missing auth: anyone can read orders
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    print(json.dumps({"logger": "restapi-lab", "message": "mock REST API on :8080 (mode=broken)"}))
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
