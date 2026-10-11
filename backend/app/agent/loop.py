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
from app.tools.supabase import (
    AnonReadArgs,
    AuthReadArgs,
    classify_client_key,
    review_rls_configuration,
    test_authenticated_tenant_isolation,
    test_scoped_anonymous_read,
)
from app.verify import verify_anonymous_read, verify_tenant_isolation

logger = logging.getLogger("agent")

_BASE_TOOLS = ["classify_client_key", "test_scoped_anonymous_read"]


def _available_tools(scope: ScopeConfig) -> list[str]:
    tools = list(_BASE_TOOLS)
    if scope.authenticated_test_accounts:
        tools.append("test_authenticated_tenant_isolation")  # Check C
    if scope.admin_dsn:
        tools.append("review_rls_configuration")  # Check D
    return tools


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
    tool_specs = {
        "classify_client_key": {
            "arguments": {},
            "note": "classifies the discovered client key offline; no arguments needed",
        },
        "test_scoped_anonymous_read": {
            "arguments": {"base_url": "one of discovered_endpoints", "table": "one of discovered_tables"},
            "note": "anonymous read of ONE table; the client key is supplied automatically",
        },
    }
    if scope.authenticated_test_accounts:
        tool_specs["test_authenticated_tenant_isolation"] = {
            "arguments": {"base_url": "one of discovered_endpoints", "table": "one of discovered_tables"},
            "note": "reads a table as an authorized authenticated test user and checks whether "
                    "other tenants' rows are visible (cross-tenant isolation). Account supplied automatically.",
        }
    if scope.admin_dsn:
        tool_specs["review_rls_configuration"] = {
            "arguments": {},
            "note": "with authorized admin DB access, reviews RLS enabled/policies per discovered table",
        }
    return {
        "scope": {
            "active_testing_allowed": scope.active_testing_allowed,
            "authorized_hosts": scope.authorized_hosts,
            "authorized_resources": scope.authorized_resources,
            "allow_lab_targets": scope.allow_lab_targets,
            "requests_remaining": scope.max_active_requests - used,
            "authenticated_test_accounts_available": len(scope.authenticated_test_accounts),
            "admin_access_available": bool(scope.admin_dsn),
        },
        "discovered_endpoints": ids("endpoint"),
        "discovered_tables": ids("table"),
        "discovered_keys_masked": [k[:12] + "…" for k in keys],
        "available_tools": tool_specs,
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
    endpoints = [r.identifier for r in resources if r.resource_type == "endpoint"]

    def resolve_base_url(args: dict[str, Any]) -> str:
        """Ground the endpoint in the DISCOVERED attack surface, tolerating arg variants.
        The LLM must not invent a URL; we map its hint to a discovered endpoint."""
        hint = args.get("base_url") or args.get("url") or args.get("host") or ""
        for ep in endpoints:
            if hint and (hint == ep or urlparse(ep).hostname == hint or hint in ep):
                return ep
        return endpoints[0] if endpoints else hint

    def resolve_table(args: dict[str, Any]) -> str:
        return args.get("table") or str(args.get("resource", "")).split(":")[-1]

    tools = _available_tools(scope)
    accounts = scope.authenticated_test_accounts
    used = 0
    findings = 0
    prior: list[str] = []
    schema = decision_schema(tools)
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

        if decision.action not in tools:
            _record(session, assessment_id, step, decision.action, decision.arguments,
                    "invalid_decision", detail="unregistered or unavailable tool")
            continue

        # --- classify_client_key: offline, informational ---
        if decision.action == "classify_client_key":
            key = decision.arguments.get("key") or anon_key
            info = classify_client_key(key)
            # Feed the observation back so the planner doesn't repeat the classification.
            prior[-1] += f" -> {info['classification']}"
            _record(session, assessment_id, step, decision.action, decision.arguments, "ok",
                    outcome="classified", rationale=decision.rationale,
                    detail=json.dumps(info))
            continue

        # --- review_rls_configuration (Check D): admin metadata review, no HTTP ---
        if decision.action == "review_rls_configuration":
            tables = [r.identifier for r in resources if r.resource_type == "table"]
            res = review_rls_configuration(scope.admin_dsn, tables)
            outcome = "reviewed" if res.ok else "tool_failure"
            execution = _record(session, assessment_id, step, decision.action, decision.arguments,
                                "ok" if res.ok else "tool_failed", outcome=outcome,
                                rationale=decision.rationale, detail=json.dumps(res.evidence))
            prior[-1] += f" -> {outcome}"
            if res.ok:
                for tname, info in (res.evidence.get("rls", {})).items():
                    if info.get("rls_enabled") is False:
                        findings += 1
                        _create_rls_finding(session, assessment_id, execution.id, tname, info)
            continue

        # --- active checks on a table: anonymous read (Check B) or tenant isolation (Check C) ---
        base_url = resolve_base_url(decision.arguments)
        table = resolve_table(decision.arguments)
        host = urlparse(base_url).hostname
        action = ProposedAction(
            tool=decision.action, is_active_network=True,
            target_url=f"{base_url.rstrip('/')}/{table}", target_host=host,
            resource_id=f"table:{table}", method="GET",
        )
        gate = evaluate(action, scope, active_requests_used=used, resolver=resolver)
        if not gate.allowed:
            prior[-1] += f" -> blocked ({gate.code})"
            _record(session, assessment_id, step, decision.action, decision.arguments,
                    "gate_denied", gate_code=gate.code, rationale=decision.rationale,
                    detail=gate.reason)
            continue

        used += 1
        if decision.action == "test_authenticated_tenant_isolation":
            acct = accounts[0]  # authorized test account supplied by scope, not the LLM
            res = test_authenticated_tenant_isolation(
                AuthReadArgs(base_url=base_url, table=table, user_jwt=acct["jwt"],
                             own_tenant_id=acct["tenant_id"]), scope, resolver=resolver)
            verdict = verify_tenant_isolation(res)
        else:  # test_scoped_anonymous_read
            res = test_scoped_anonymous_read(
                AnonReadArgs(base_url=base_url, table=table, anon_key=anon_key), scope,
                resolver=resolver)
            verdict = verify_anonymous_read(res)

        prior[-1] += f" -> {table}: {verdict.outcome}"
        execution = _record(
            session, assessment_id, step, decision.action, decision.arguments, "ok",
            outcome=verdict.outcome, rationale=decision.rationale, detail=verdict.rationale,
        )
        if verdict.is_finding:
            findings += 1
            if verdict.outcome == "cross_tenant_access":
                _create_cross_tenant_finding(session, assessment_id, execution.id, base_url,
                                             table, res.evidence)
            else:
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


def _create_cross_tenant_finding(session: Session, assessment_id: str, execution_id: str,
                                 base_url: str, table: str, evidence: dict) -> None:
    session.add(Finding(
        assessment_id=assessment_id, execution_id=execution_id,
        title=f"Cross-tenant data access in '{table}' (authenticated)",
        severity="high", status="confirmed", confidence="high", evidence_quality="strong",
        affected_resource=f"{base_url.rstrip('/')}/{table}",
        impact=(
            f"An authenticated test user read rows belonging to OTHER tenants from '{table}'. "
            "Tenant isolation is not enforced; any authenticated user can access other "
            "customers' data."
        ),
        remediation=(
            f"Add a Row Level Security policy on '{table}' that scopes rows to the caller's "
            "tenant (e.g. tenant_id = the JWT tenant claim); re-test with multiple tenants."
        ),
        evidence_json=json.dumps(evidence),
    ))


def _create_rls_finding(session: Session, assessment_id: str, execution_id: str,
                        table: str, info: dict) -> None:
    session.add(Finding(
        assessment_id=assessment_id, execution_id=execution_id,
        title=f"Row Level Security disabled on '{table}'",
        severity="medium", status="confirmed", confidence="high", evidence_quality="strong",
        affected_resource=f"table:{table}",
        impact=(
            f"Admin metadata review shows RLS is disabled on '{table}', so row-level access "
            "controls are not enforced for this table at the database layer."
        ),
        remediation=(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY and define explicit policies; "
            "verify PostgreSQL grants do not bypass RLS."
        ),
        evidence_json=json.dumps({"admin_metadata": info}),
    ))
