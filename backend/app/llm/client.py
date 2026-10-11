"""LLM client: talks to the gateway (real Claude) or a stub (tests / no-LLM mode).

Selected by env `LLM_MODE`:
  - "gateway": POST to the llm-gateway (real Claude).
  - "stub"   : a scripted in-process double; no network, deterministic.

Deterministic static analysis must work with no LLM configured, so "stub" (or simply
not running the agent) is always a valid mode.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.llm.schema import AgentDecision


@dataclass
class DecisionResult:
    decision: AgentDecision
    usage: dict | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None


class LLMError(Exception):
    def __init__(self, message: str, category: str = "llm_error") -> None:
        super().__init__(message)
        self.category = category


class LLMClient(Protocol):
    def decide(self, system: str, prompt: str, json_schema: dict) -> DecisionResult: ...


class GatewayLLMClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self._url = base_url.rstrip("/")
        self._timeout = timeout

    def decide(self, system: str, prompt: str, json_schema: dict) -> DecisionResult:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._url}/decide",
                    json={"system": system, "prompt": prompt, "json_schema": json_schema},
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"gateway unreachable: {exc}", "network") from exc

        body = resp.json()
        if not body.get("ok"):
            raise LLMError(body.get("error", "gateway error"), body.get("category", "llm_error"))
        # The model output is validated against our Pydantic model (defence in depth:
        # malformed output is rejected, never coerced).
        decision = AgentDecision.model_validate(body["decision"])
        return DecisionResult(
            decision=decision,
            usage=body.get("usage"),
            cost_usd=body.get("cost_usd"),
            duration_ms=body.get("duration_ms"),
        )


class StubLLMClient:
    """A scripted double. `script` maps an iteration index to a decision dict, or a
    callable receives (system, prompt) and returns a decision dict."""

    def __init__(self, script: Callable[[str, str], dict[str, Any]]) -> None:
        self._script = script

    def decide(self, system: str, prompt: str, json_schema: dict) -> DecisionResult:
        raw = self._script(system, prompt)
        return DecisionResult(decision=AgentDecision.model_validate(raw))


def get_llm_client() -> LLMClient | None:
    """Build the configured client, or None when the agent/LLM is disabled."""
    mode = os.environ.get("LLM_MODE", "disabled")
    if mode == "gateway":
        url = os.environ.get("LLM_GATEWAY_URL", "http://llm-gateway:9000")
        return GatewayLLMClient(url)
    if mode == "stub":
        # Default stub: always stop (safe no-op). Tests inject their own scripts.
        return StubLLMClient(lambda s, p: {
            "objective": "no-op", "action": "stop", "expected_observation": "n/a",
            "rationale": "stub client", "stop_reason": "stub mode",
        })
    return None
