"""Mock Firebase Realtime Database REST endpoint for the lab.

A faithful, deterministic stand-in for the RTDB REST contract (`GET /<path>.json`), so the
anonymous-read check can be tested against known answers. The assessment tool speaks the
REAL RTDB protocol, so it works against actual Firebase too — this mock just lets us flip
between known-good and known-bad rules without a heavy emulator. Synthetic data only.

Modes:
  broken  : open read rules — GET /<path>.json returns data to anyone (the classic bug).
  correct : locked rules    — returns 401 {"error":"Permission denied"}.

Lab-only control endpoint: POST /__mode/broken|correct  (not part of the RTDB contract).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Synthetic data keyed by RTDB path.
_DATA = {
    "users": {"u1": {"email": "ana@acme.test", "plan": "pro"},
              "u2": {"email": "glen@globex.test", "plan": "free"}},
    "messages": {"m1": {"from": "u1", "text": "hello"}},
}
_mode = {"value": "broken"}


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: object) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
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
        from urllib.parse import urlparse

        route = urlparse(self.path).path  # drop any query string (e.g. ?shallow=true)
        if route == "/__mode":
            self._json(200, {"mode": _mode["value"]})
            return
        if not route.endswith(".json"):
            self._json(404, {"error": "RTDB paths end in .json"})
            return
        # Locked rules: deny anonymous reads (what a correctly-configured DB does).
        if _mode["value"] == "correct":
            self._json(401, {"error": "Permission denied"})
            return
        # Open rules: return the data at the requested path.
        path = route[1:-5].strip("/")  # strip leading / and trailing .json
        node: object = _DATA
        for part in [p for p in path.split("/") if p]:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        self._json(200, node)

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    print(json.dumps({"logger": "firebase-lab", "message": "mock RTDB on :9000 (mode=broken)"}))
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()


if __name__ == "__main__":
    main()
