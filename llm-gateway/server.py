"""LLM gateway: prompt in, schema-validated JSON decision out.

The ONLY component that holds LLM credentials (ADR-003/015). It shells out to the
Claude CLI with all built-in tools hardcoded OFF, from an empty working directory, so a
prompt-injection in the input can never reach a shell, the filesystem, or the network.

Contract:
  POST /decide  {system, prompt, json_schema, model?}  ->
      {ok, decision, usage, cost_usd, duration_ms}  | {ok:false, error, category}

It never logs prompt contents — only metadata (usage, cost, duration).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = os.environ.get("LLM_MODEL", "sonnet")
TIMEOUT = int(os.environ.get("LLM_TIMEOUT_SECONDS", "90"))
MAX_CONCURRENCY = int(os.environ.get("LLM_MAX_CONCURRENCY", "1"))
_SEM = threading.Semaphore(MAX_CONCURRENCY)

# Hardcoded isolation flags (Spike 001). Callers cannot change these.
_SAFE_FLAGS = [
    "--tools", "",
    "--strict-mcp-config",
    "--setting-sources", "",
    "--no-session-persistence",
    "--output-format", "json",
]


def _log(message: str, **extra: object) -> None:
    print(json.dumps({"logger": "llm-gateway", "message": message, **extra}))


def run_claude(system: str, prompt: str, json_schema: dict, model: str) -> dict:
    """Invoke the Claude CLI in an empty temp dir; return the parsed result envelope."""
    with tempfile.TemporaryDirectory() as workdir:
        schema_path = os.path.join(workdir, "schema.json")
        with open(schema_path, "w") as f:
            json.dump(json_schema, f)

        cmd = [
            "claude", "-p", prompt,
            "--system-prompt", system,
            "--model", model,
            "--json-schema", schema_path,
            *_SAFE_FLAGS,
        ]
        started = time.monotonic()
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        duration_ms = int((time.monotonic() - started) * 1000)

    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[:300]}")

    if not proc.stdout.strip():
        # Empty stdout with --json-schema typically means the CLI is not authenticated.
        raise RuntimeError(
            "claude produced no output — the gateway is likely unauthenticated "
            "(set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY; see ADR-015)"
        )

    data = json.loads(proc.stdout)
    # Claude can exit 0 while reporting an error in the envelope (e.g. auth failure).
    if data.get("is_error"):
        raise RuntimeError(f"claude error: {data.get('result', 'unknown')[:200]}")
    decision = data.get("structured_output")
    if decision is None:
        raise ValueError("no structured_output in claude response")
    return {
        "decision": decision,
        "usage": data.get("usage"),
        "cost_usd": data.get("total_cost_usd"),
        "duration_ms": data.get("duration_ms", duration_ms),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, {"status": "ok", "role": "llm-gateway", "model": MODEL})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/decide":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            req = json.loads(self.rfile.read(length) or "{}")
            system = req["system"]
            prompt = req["prompt"]
            schema = req["json_schema"]
            model = req.get("model", MODEL)
        except (json.JSONDecodeError, KeyError) as exc:
            self._send(400, {"ok": False, "error": f"bad request: {exc}", "category": "bad_request"})
            return

        acquired = _SEM.acquire(timeout=TIMEOUT)
        if not acquired:
            self._send(503, {"ok": False, "error": "gateway busy", "category": "busy"})
            return
        try:
            result = run_claude(system, prompt, schema, model)
            _log("decide ok", duration_ms=result["duration_ms"], cost_usd=result["cost_usd"])
            self._send(200, {"ok": True, **result})
        except subprocess.TimeoutExpired:
            _log("decide timeout")
            self._send(504, {"ok": False, "error": "llm timeout", "category": "timeout"})
        except Exception as exc:  # noqa: BLE001
            _log("decide error", error=type(exc).__name__)
            self._send(502, {"ok": False, "error": str(exc)[:300], "category": "llm_error"})
        finally:
            _SEM.release()

    def log_message(self, *args: object) -> None:  # silence default access log
        pass


def main() -> None:
    _log("gateway starting", model=MODEL, port=9000)
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()


if __name__ == "__main__":
    main()
