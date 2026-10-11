"""Scope configuration and the proposed-action / decision types.

The scope configuration is the authoritative statement of what an assessment may do.
It is set by the operator (not the LLM) and stored on the assessment as JSON.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScopeConfig(BaseModel):
    """What this assessment is authorized to do. Default-deny for active testing."""

    model_config = ConfigDict(extra="forbid")

    owner: str = "local-operator"
    environment: Literal["local", "staging", "production"] = "local"

    # Active (network) testing is off unless explicitly enabled.
    active_testing_allowed: bool = False

    # Hostnames explicitly authorized as active targets.
    authorized_hosts: list[str] = Field(default_factory=list)
    # Resource identifiers explicitly approved, e.g. "table:trips".
    authorized_resources: list[str] = Field(default_factory=list)

    # The loopback/private-range exception for a controlled local lab (ADR-001).
    allow_lab_targets: bool = False

    # Read-only by default; mutating methods require explicit widening + approval.
    permitted_methods: list[str] = Field(default_factory=lambda: ["GET", "HEAD"])

    # Operations that require a human approval even when otherwise in scope.
    require_approval_for: list[str] = Field(default_factory=list)

    # Hard ceiling on active requests for this assessment (ADR-011).
    max_active_requests: int = 30

    def resource_approved(self, resource_id: str | None) -> bool:
        return resource_id is not None and resource_id in self.authorized_resources

    def host_authorized(self, host: str | None) -> bool:
        return host is not None and host in self.authorized_hosts


class ProposedAction(BaseModel):
    """A single action the planner proposes. Validated before it can run."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    is_active_network: bool = False
    target_host: str | None = None
    target_url: str | None = None
    resource_id: str | None = None
    method: str = "GET"


class GateDecision(BaseModel):
    allowed: bool
    code: str
    reason: str

    @classmethod
    def allow(cls, reason: str = "within scope") -> GateDecision:
        return cls(allowed=True, code="ok", reason=reason)

    @classmethod
    def deny(cls, code: str, reason: str) -> GateDecision:
        return cls(allowed=False, code=code, reason=reason)
