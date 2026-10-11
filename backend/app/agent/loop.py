"""The bounded agent loop.

The planner (LLM) proposes one decision at a time. Deterministic code then validates it,
runs it through the scope gate, executes the registered tool, and the verifier classifies
the real result. Findings are created only from verified evidence. Every step is persisted
as a ToolExecution (auditable), and the loop always terminates (step/budget caps).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.llm.client import LLMClient, LLMError
from app.llm.prompts import PLANNER_SYSTEM, render_planner_prompt
from app.llm.schema import decision_schema
from app.models import AttackSurfaceResource, Finding, ToolExecution
from app.scope.config import ProposedAction, ScopeConfig
from app.scope.gate import Resolver, default_resolver, evaluate
from app.tools.supabase import AnonReadArgs, classify_client_key, test_scoped_anonymous_read
from app.verify import verify_anonymous_read

logger = logging.getLogger("agent")

_TOOLS = ["classify_client_key", "test_scoped_anonymous_read"]


@dataclass
class LoopSummary:
    steps: int
    findings: int
    stop_reason: str


def _load_resources(session: Session, assessment_id: str) -> list[AttackSurfaceResource]:
    return (
        session.query(AttackSurfaceResource).filter_by(assessment_id=assessment_id).all()
    )


def _build_state(scope: ScopeConfig, resources: list[AttackSurfaceResource],
                 used: int, prior: list[str]) -> dict[str, Any]:
    def ids(t: str) -> list[str]:
        return [r.identifier for r in resources if r.resource_type == t]

    # Keys are shown masked to the model; the loop holds the real value out-of-band.
    keys = [r.identifier for r in resources if r.resource_type == "key"]
    return {
        "scope": {
            "active_testing_allowed": scope.active_testing_allowed,
            "authorized_hosts": scope.authorized_hosts,
            "authorized_resources": scope.authorized_resources,
            "allow_lab_targets": scope.allow_lab_targets,
            "requests_remaining": scope.max_active_requests - used,
        },
        "discovered_endpoints": ids("endpoint"),
        "discovered_tables": ids("table"),
        "discovered_keys_masked": [k[:12] + "…" for k in keys],
        "available_tools": _TOOLS,
        "prior_steps": prior,
    }


def run_assessment_loop(
    session: Session,
    assessment_id: str,
    llm_client: LLMClient,
    *,
    resolver: Resolver = default_resolver,
    max_steps: int = 15,
) -> LoopSummary:
    from app.models import Assessment

    assessment = session.get(Assessment, assessment_id)
    if assessment is None:
        return LoopSummary(0, 0, "assessment_not_found")
    scope = ScopeConfig(**json.loads(assessment.scope_configuration or "{}"))
    resources = _load_resources(session, assessment_id)

    # Real public key held out-of-band (never surfaced to the model in full).
    public_keys = [r.identifier for r in resources if r.resource_type == "key"]
    anon_key = public_keys[0] if public_keys else ""

    used = 0
    findings = 0
    prior: list[str] = []
    schema = decision_schema(_TOOLS)
    stop_reason = "step_cap"

    for step in range(max_steps):
        state = _build_state(scope, resources, used, prior)
        try:
            result = llm_client.decide(
                PLANNER_SYSTEM, render_planner_prompt(json.dumps(state, indent=1)), schema
            )
        except LLMError as exc:
            _record(session, assessment_id, step, "(llm)", None, "invalid_decision",
                    detail=f"LLM error: {exc}")
            stop_reason = "llm_error"
            break

        decision = result.decision
        prior.append(f"{decision.action}: {decision.objective}")

        if decision.action == "stop":
            _record(session, assessment_id, step, "stop", None, "stopped",
                    rationale=decision.rationale, detail=decision.stop_reason)
            stop_reason = decision.stop_reason or "planner_stop"
            break

        if decision.action not in _TOOLS:
            _record(session, assessment_id, step, decision.action, decision.arguments,
                    "invalid_decision", detail="unregistered tool")
            continue

        # --- classify_client_key: offline, informational ---
        if decision.action == "classify_client_key":
            key = decision.arguments.get("key") or anon_key
            info = classify_client_key(key)
            _record(session, assessment_id, step, decision.action, decision.arguments, "ok",
                    outcome="classified", rationale=decision.rationale,
                    detail=json.dumps(info))
            continue

        # --- test_scoped_anonymous_read: active, gated, verified ---
        base_url = decision.arguments.get("base_url", "")
        table = decision.arguments.get("table", "")
        host = urlparse(base_url).hostname
        action = ProposedAction(
            tool=decision.action, is_active_network=True,
            target_url=f"{base_url.rstrip('/')}/{table}", target_host=host,
            resource_id=f"table:{table}", method="GET",
        )
        gate = evaluate(action, scope, active_requests_used=used, resolver=resolver)
        if not gate.allowed:
            _record(session, assessment_id, step, decision.action, decision.arguments,
                    "gate_denied", gate_code=gate.code, rationale=decision.rationale,
                    detail=gate.reason)
            continue

        used += 1
        res = test_scoped_anonymous_read(
            AnonReadArgs(base_url=base_url, table=table, anon_key=anon_key), scope,
            resolver=resolver,
        )
        verdict = verify_anonymous_read(res)
        execution = _record(
            session, assessment_id, step, decision.action, decision.arguments, "ok",
            outcome=verdict.outcome, rationale=decision.rationale,
            detail=verdict.rationale,
        )
        if verdict.is_finding:
            findings += 1
            _create_finding(session, assessment_id, execution.id, base_url, table, res.evidence)

        if used >= scope.max_active_requests:
            stop_reason = "budget_exhausted"
            break

    session.commit()
    logger.info("assessment loop done",
                extra={"extra": {"assessment_id": assessment_id, "findings": findings,
                                 "stop": stop_reason}})
    return LoopSummary(steps=step + 1, findings=findings, stop_reason=stop_reason)


def _record(session: Session, assessment_id: str, step: int, tool: str,
            arguments: dict | None, status: str, *, gate_code: str | None = None,
            outcome: str | None = None, rationale: str | None = None,
            detail: str | None = None) -> ToolExecution:
    ex = ToolExecution(
        assessment_id=assessment_id, step_index=step, tool_name=tool,
        arguments_json=json.dumps(arguments) if arguments is not None else None,
        status=status, gate_code=gate_code, outcome=outcome, rationale=rationale,
        detail=detail,
    )
    session.add(ex)
    session.flush()
    return ex


def _create_finding(session: Session, assessment_id: str, execution_id: str,
                    base_url: str, table: str, evidence: dict) -> None:
    session.add(Finding(
        assessment_id=assessment_id,
        execution_id=execution_id,
        title=f"Unauthorized anonymous read of '{table}'",
        severity="high",
        status="confirmed",
        confidence="high",
        evidence_quality="strong",
        affected_resource=f"{base_url.rstrip('/')}/{table}",
        impact=(
            f"An unauthenticated client read rows from '{table}', which should be "
            "access-controlled. Any anonymous user could retrieve this data."
        ),
        remediation=(
            f"Enable Row Level Security on '{table}' and define policies that restrict "
            "anonymous access; verify PostgreSQL grants; re-test anonymous and "
            "authenticated contexts."
        ),
        evidence_json=json.dumps(evidence),
    ))
