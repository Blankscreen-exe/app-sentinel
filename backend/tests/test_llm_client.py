"""The stub LLM client and decision validation (no network)."""

from __future__ import annotations

import pytest

from app.llm.client import StubLLMClient
from app.llm.schema import AgentDecision, decision_schema


def test_stub_returns_validated_decision() -> None:
    client = StubLLMClient(lambda s, p: {
        "objective": "check anon read of trips",
        "action": "test_scoped_anonymous_read",
        "arguments": {"table": "trips"},
        "expected_observation": "rows or denial",
        "rationale": "public key + table ref suggest testing anon access",
        "uncertainty": ["backend RLS unknown"],
    })
    res = client.decide("sys", "state", decision_schema(["test_scoped_anonymous_read"]))
    assert isinstance(res.decision, AgentDecision)
    assert res.decision.action == "test_scoped_anonymous_read"


def test_decision_schema_constrains_action_enum() -> None:
    schema = decision_schema(["classify_client_key", "test_scoped_anonymous_read"])
    assert set(schema["properties"]["action"]["enum"]) == {
        "classify_client_key", "test_scoped_anonymous_read", "stop",
    }


def test_malformed_decision_rejected() -> None:
    client = StubLLMClient(lambda s, p: {"action": "stop"})  # missing required fields
    with pytest.raises(Exception):
        client.decide("sys", "state", decision_schema([]))
