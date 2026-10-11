"""The scope gate must enforce authorization deterministically, independent of any LLM.

These tests encode the security guarantees: default-deny for active testing, host and
resource authorization, SSRF / private-destination blocking, the lab exception, budget,
method, and approval gates.
"""

from __future__ import annotations

from app.scope.config import ProposedAction, ScopeConfig
from app.scope.gate import check_network_target, evaluate


def _public_resolver(host: str) -> list[str]:
    return ["93.184.216.34"]  # example.com, a public address


def _lab_resolver(host: str) -> list[str]:
    return ["172.18.0.5"]  # docker private range


# --- non-active actions always allowed (registry restricts which tools exist) ---
def test_non_active_action_allowed() -> None:
    d = evaluate(ProposedAction(tool="classify_client_key"), ScopeConfig())
    assert d.allowed


# --- default-deny: active testing off by default ---
def test_active_denied_when_testing_disabled() -> None:
    action = ProposedAction(tool="anon_read", is_active_network=True, target_host="x.supabase.co")
    d = evaluate(action, ScopeConfig(active_testing_allowed=False))
    assert not d.allowed and d.code == "active_testing_disabled"


# --- host must be authorized ---
def test_unauthorized_host_denied() -> None:
    scope = ScopeConfig(active_testing_allowed=True, authorized_hosts=["allowed.supabase.co"])
    action = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="https://evil.example.com/x"
    )
    d = evaluate(action, scope, resolver=_public_resolver)
    assert not d.allowed and d.code == "host_not_authorized"


def test_authorized_public_host_allowed() -> None:
    scope = ScopeConfig(active_testing_allowed=True, authorized_hosts=["example.com"])
    action = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="https://example.com/rest"
    )
    d = evaluate(action, scope, resolver=_public_resolver)
    assert d.allowed, d.reason


# --- SSRF / DNS-rebinding: private destination blocked unless lab authorized ---
def test_private_destination_blocked_by_default() -> None:
    scope = ScopeConfig(active_testing_allowed=True, authorized_hosts=["lab-rest"])
    action = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="http://lab-rest:3000/trips"
    )
    d = evaluate(action, scope, resolver=_lab_resolver)
    assert not d.allowed and d.code == "blocked_private_destination"


def test_private_destination_allowed_for_authorized_lab() -> None:
    scope = ScopeConfig(
        active_testing_allowed=True, authorized_hosts=["lab-rest"], allow_lab_targets=True
    )
    action = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="http://lab-rest:3000/trips"
    )
    d = evaluate(action, scope, resolver=_lab_resolver)
    assert d.allowed, d.reason


def test_lab_exception_still_requires_authorized_host() -> None:
    # allow_lab_targets does not waive host authorization.
    scope = ScopeConfig(active_testing_allowed=True, authorized_hosts=[], allow_lab_targets=True)
    action = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="http://lab-rest:3000/trips"
    )
    d = evaluate(action, scope, resolver=_lab_resolver)
    assert not d.allowed and d.code == "host_not_authorized"


# --- scheme, budget, method, approval ---
def test_bad_scheme_denied() -> None:
    scope = ScopeConfig(active_testing_allowed=True, authorized_hosts=["h"])
    d = check_network_target("file:///etc/passwd", scope, resolver=_public_resolver)
    assert not d.allowed and d.code == "bad_scheme"


def test_budget_exhausted_denied() -> None:
    scope = ScopeConfig(
        active_testing_allowed=True, authorized_hosts=["example.com"], max_active_requests=5
    )
    action = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="https://example.com/x"
    )
    d = evaluate(action, scope, active_requests_used=5, resolver=_public_resolver)
    assert not d.allowed and d.code == "budget_exhausted"


def test_method_not_permitted_denied() -> None:
    scope = ScopeConfig(
        active_testing_allowed=True, authorized_hosts=["example.com"], permitted_methods=["GET"]
    )
    action = ProposedAction(
        tool="mutate", is_active_network=True, target_url="https://example.com/x", method="DELETE"
    )
    d = evaluate(action, scope, resolver=_public_resolver)
    assert not d.allowed and d.code == "method_not_permitted"


def test_approval_required_denied() -> None:
    scope = ScopeConfig(
        active_testing_allowed=True,
        authorized_hosts=["example.com"],
        require_approval_for=["mutate"],
    )
    action = ProposedAction(
        tool="mutate", is_active_network=True, target_url="https://example.com/x"
    )
    d = evaluate(action, scope, resolver=_public_resolver)
    assert not d.allowed and d.code == "approval_required"


def test_resource_must_be_approved() -> None:
    scope = ScopeConfig(
        active_testing_allowed=True,
        authorized_hosts=["example.com"],
        authorized_resources=["table:trips"],
    )
    ok = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="https://example.com/trips",
        resource_id="table:trips",
    )
    bad = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="https://example.com/secrets",
        resource_id="table:secrets",
    )
    assert evaluate(ok, scope, resolver=_public_resolver).allowed
    d = evaluate(bad, scope, resolver=_public_resolver)
    assert not d.allowed and d.code == "resource_not_approved"


def test_suffix_wildcard_host_authorized() -> None:
    scope = ScopeConfig(active_testing_allowed=True, authorized_hosts=["*.supabase.co"])
    assert scope.host_authorized("abcd1234.supabase.co")
    assert not scope.host_authorized("evil.example.com")
    assert not scope.host_authorized("notsupabase.co")


def test_bare_star_authorizes_any_host() -> None:
    scope = ScopeConfig(active_testing_allowed=True, authorized_hosts=["*"])
    assert scope.host_authorized("anything.example.com")
    assert scope.wildcard_all


def test_bare_star_still_blocks_private_destinations() -> None:
    # '*' removes the host allowlist but NOT the SSRF / private-IP guard.
    scope = ScopeConfig(active_testing_allowed=True, authorized_hosts=["*"])
    action = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="http://internal.local/x"
    )
    d = evaluate(action, scope, resolver=_lab_resolver)  # resolves to a private IP
    assert not d.allowed and d.code == "blocked_private_destination"


def test_bare_star_allows_public_host() -> None:
    scope = ScopeConfig(active_testing_allowed=True, authorized_hosts=["*"])
    action = ProposedAction(
        tool="anon_read", is_active_network=True, target_url="https://anything.example.com/x"
    )
    assert evaluate(action, scope, resolver=_public_resolver).allowed
