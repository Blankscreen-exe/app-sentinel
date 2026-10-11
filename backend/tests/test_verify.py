"""Key classification and the verifier's deterministic outcome mapping."""

from __future__ import annotations

from app.tools.base import ToolResult
from app.tools.supabase import classify_client_key
from app.verify import verify_anonymous_read


def test_classify_publishable_is_not_a_secret() -> None:
    r = classify_client_key("sb_publishable_abc123def456")
    assert r["classification"] == "public_client_key"
    assert r["sensitive"] is False


def test_classify_secret_key_is_sensitive() -> None:
    r = classify_client_key("sb_secret_abc123def456")
    assert r["classification"] == "secret_key"
    assert r["sensitive"] is True


def test_classify_jwt_needs_decoding() -> None:
    assert classify_client_key("eyJhbGciOi.payload.sig")["classification"] == "jwt"


def _ok(**signal: object) -> ToolResult:
    return ToolResult(ok=True, tool="test_scoped_anonymous_read", signal=signal)


def test_rows_returned_is_unauthorized_access() -> None:
    v = verify_anonymous_read(_ok(http_status=200, row_count=2, is_list=True, pg_error_code=None))
    assert v.outcome == "unauthorized_access" and v.is_finding


def test_http_403_is_access_denied() -> None:
    v = verify_anonymous_read(_ok(http_status=403, row_count=None, is_list=False))
    assert v.outcome == "access_denied" and not v.is_finding


def test_pg_error_is_access_denied() -> None:
    v = verify_anonymous_read(_ok(http_status=200, is_list=False, pg_error_code="42501"))
    assert v.outcome == "access_denied" and not v.is_finding


def test_empty_list_is_inconclusive_not_finding() -> None:
    v = verify_anonymous_read(_ok(http_status=200, row_count=0, is_list=True, pg_error_code=None))
    assert v.outcome == "empty" and not v.is_finding


def test_network_error_not_finding() -> None:
    r = ToolResult(ok=False, tool="t", error_category="network_error", signal={"error": "network:x"})
    v = verify_anonymous_read(r)
    assert v.outcome == "network_error" and not v.is_finding


def test_tool_failure_not_finding() -> None:
    r = ToolResult(ok=False, tool="t", error_category="tool_failure", signal={"error": "boom"})
    v = verify_anonymous_read(r)
    assert v.outcome == "tool_failure" and not v.is_finding


from app.verify import verify_firebase_read


def test_firebase_open_read_is_finding() -> None:
    r = _ok(http_status=200, denied=False, has_data=True)
    v = verify_firebase_read(r)
    assert v.outcome == "firebase_open_read" and v.is_finding


def test_firebase_denied_not_finding() -> None:
    r = _ok(http_status=401, denied=True, has_data=False)
    v = verify_firebase_read(r)
    assert v.outcome == "access_denied" and not v.is_finding


def test_firebase_empty_not_finding() -> None:
    r = _ok(http_status=200, denied=False, has_data=False)
    v = verify_firebase_read(r)
    assert v.outcome == "empty" and not v.is_finding


from app.verify import verify_unauthenticated_endpoint


def test_generic_endpoint_data_is_candidate_finding() -> None:
    v = verify_unauthenticated_endpoint(_ok(http_status=200, is_json=True, has_payload=True))
    assert v.outcome == "unauthenticated_endpoint_data" and v.is_finding


def test_generic_endpoint_auth_required_not_finding() -> None:
    v = verify_unauthenticated_endpoint(_ok(http_status=401, is_json=True, has_payload=False))
    assert v.outcome == "endpoint_requires_auth" and not v.is_finding


def test_generic_endpoint_no_payload_inconclusive() -> None:
    v = verify_unauthenticated_endpoint(_ok(http_status=200, is_json=False, has_payload=False))
    assert v.outcome == "inconclusive" and not v.is_finding
