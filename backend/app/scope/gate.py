"""The scope gate and network guard — pure, deterministic, testable without the LLM.

`evaluate` is the single authorization decision point. Every active action must pass it
before execution. The network guard resolves the target host and refuses private /
loopback / link-local / reserved destinations unless the assessment explicitly authorizes
a controlled lab target — mitigating SSRF and DNS-rebinding.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from collections.abc import Callable
from urllib.parse import urlparse

from app.scope.config import GateDecision, ProposedAction, ScopeConfig

logger = logging.getLogger("scope.gate")

# A resolver maps a hostname to a list of IP strings. Injectable for testing.
Resolver = Callable[[str], list[str]]


def default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return [info[4][0] for info in infos]


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def check_network_target(
    url_or_host: str,
    scope: ScopeConfig,
    *,
    resolver: Resolver = default_resolver,
) -> GateDecision:
    """Validate a network destination: scheme, host authorization, resolved IP range."""
    host = url_or_host
    if "://" in url_or_host:
        parsed = urlparse(url_or_host)
        if parsed.scheme not in ("http", "https"):
            return GateDecision.deny("bad_scheme", f"scheme {parsed.scheme!r} not allowed")
        host = parsed.hostname or ""

    if not host:
        return GateDecision.deny("no_host", "no host in target")

    if not scope.host_authorized(host):
        return GateDecision.deny("host_not_authorized", f"host {host!r} is not in scope")

    if scope.wildcard_all:
        # The per-host allowlist is disabled by '*'. Make this visible; the SSRF guard
        # below still blocks private/loopback/reserved unless lab targets are authorized.
        logger.warning(
            "wildcard host authorization in effect ('*'): %s allowed by match-all", host,
            extra={"extra": {"host": host, "wildcard_all": True}},
        )

    try:
        ips = resolver(host)
    except Exception as exc:  # noqa: BLE001
        return GateDecision.deny("dns_error", f"could not resolve {host!r}: {exc}")

    if not ips:
        return GateDecision.deny("dns_error", f"no addresses for {host!r}")

    for ip in ips:
        if _is_blocked_ip(ip):
            # Private/loopback is allowed only for an explicitly authorized lab target.
            if scope.allow_lab_targets:
                continue
            return GateDecision.deny(
                "blocked_private_destination",
                f"{host!r} resolves to non-public address {ip} and lab targets are not authorized",
            )
    return GateDecision.allow(f"{host!r} resolves to in-scope address(es)")


def evaluate(
    action: ProposedAction,
    scope: ScopeConfig,
    *,
    active_requests_used: int = 0,
    resolver: Resolver = default_resolver,
) -> GateDecision:
    """Authorize (or refuse) a proposed action against the scope. Default-deny for active."""
    # Non-network actions (reading model state, classifying a key offline) are allowed;
    # the tool registry still restricts which tools exist (enforced separately).
    if not action.is_active_network:
        return GateDecision.allow("non-active action")

    if not scope.active_testing_allowed:
        return GateDecision.deny("active_testing_disabled", "active testing is not authorized")

    if action.method.upper() not in {m.upper() for m in scope.permitted_methods}:
        return GateDecision.deny("method_not_permitted", f"method {action.method!r} not permitted")

    if action.tool in scope.require_approval_for:
        return GateDecision.deny("approval_required", f"{action.tool!r} requires human approval")

    if active_requests_used >= scope.max_active_requests:
        return GateDecision.deny(
            "budget_exhausted",
            f"active request budget exhausted ({active_requests_used}/{scope.max_active_requests})",
        )

    # A resource target must be an approved resource, unless its host is authorized.
    target = action.target_url or action.target_host
    if target is None:
        if not scope.resource_approved(action.resource_id):
            return GateDecision.deny("resource_not_approved", "no in-scope target or resource")
        return GateDecision.allow("approved resource, no network target")

    net = check_network_target(target, scope, resolver=resolver)
    if not net.allowed:
        return net

    # If a specific resource is named, it must be approved too.
    if action.resource_id and not scope.resource_approved(action.resource_id):
        return GateDecision.deny("resource_not_approved", f"resource {action.resource_id!r} not approved")

    return GateDecision.allow("active action within scope")
