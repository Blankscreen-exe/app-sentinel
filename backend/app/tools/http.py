"""Scope-safe HTTP for active tools.

Redirects are NOT followed automatically; each redirect target is re-validated against
the scope gate (a hostname that passed validation must not bounce to a blocked one).
Responses are size-capped. This is the only path active tools use to touch the network.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.scope.config import ScopeConfig
from app.scope.gate import Resolver, check_network_target, default_resolver

_MAX_RESPONSE_BYTES = 256 * 1024
_MAX_REDIRECTS = 3


@dataclass
class HttpOutcome:
    ok: bool
    status: int | None
    body_text: str | None
    error: str | None = None


def safe_get(
    url: str,
    scope: ScopeConfig,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    resolver: Resolver = default_resolver,
) -> HttpOutcome:
    """GET with scope re-validation on every hop, no auto-redirects, capped body."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        gate = check_network_target(current, scope, resolver=resolver)
        if not gate.allowed:
            return HttpOutcome(ok=False, status=None, body_text=None, error=f"scope:{gate.code}")
        try:
            with httpx.Client(follow_redirects=False, timeout=timeout) as client:
                resp = client.get(current, headers=headers or {})
        except httpx.HTTPError as exc:
            return HttpOutcome(ok=False, status=None, body_text=None, error=f"network:{type(exc).__name__}")

        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                return HttpOutcome(ok=False, status=resp.status_code, body_text=None, error="redirect_no_location")
            current = str(httpx.URL(current).join(location))
            continue

        body = resp.content[:_MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")
        return HttpOutcome(ok=True, status=resp.status_code, body_text=body)

    return HttpOutcome(ok=False, status=None, body_text=None, error="too_many_redirects")
