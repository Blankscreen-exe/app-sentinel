"""Assessment report builder.

Assembles a report strictly from persisted state (findings, executions, resources) so
it never claims more than the evidence supports. No numeric security score (undefined
scoring is dishonest); "no findings" is explicitly not "secure".
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    ApplicationArtifact,
    Assessment,
    AttackSurfaceResource,
    Finding,
    ToolExecution,
)


def build_report(session: Session, assessment_id: str) -> dict[str, Any]:
    assessment = session.get(Assessment, assessment_id)
    if assessment is None:
        raise ValueError("assessment not found")
    artifact = session.get(ApplicationArtifact, assessment.artifact_id)
    findings = session.query(Finding).filter_by(assessment_id=assessment_id).all()
    execs = (
        session.query(ToolExecution)
        .filter_by(assessment_id=assessment_id)
        .order_by(ToolExecution.step_index)
        .all()
    )
    resources = session.query(AttackSurfaceResource).filter_by(assessment_id=assessment_id).all()

    scope = json.loads(assessment.scope_configuration or "{}")
    confirmed = [f for f in findings if f.status == "confirmed"]

    # Coverage from the actual execution record. Active = any network check tool.
    _ACTIVE_TOOLS = {
        "test_scoped_anonymous_read",
        "test_authenticated_tenant_isolation",
        "test_firebase_rtdb_read",
        "test_unauthenticated_endpoint",
    }
    active = [e for e in execs if e.tool_name in _ACTIVE_TOOLS]
    tested_tables = sorted(
        {_arg(e, "table") for e in active if e.status == "ok" and _arg(e, "table")}
    )
    discovered_tables = sorted({r.identifier for r in resources if r.resource_type == "table"})
    coverage = {
        "checks_completed": sum(1 for e in active if e.status == "ok"),
        "checks_blocked_by_scope": sum(1 for e in execs if e.status == "gate_denied"),
        "checks_failed": sum(1 for e in execs if e.status in ("tool_failed", "invalid_decision")),
        "checks_inconclusive": sum(1 for e in active if e.outcome in ("empty", "inconclusive")),
        "resources_discovered": len(resources),
        "tables_discovered": discovered_tables,
        "tables_assessed": tested_tables,
        "tables_not_assessed": [t for t in discovered_tables if t not in tested_tables],
    }

    limitations = [
        "Static analysis only inspects the artifact; it does not run the application.",
        "Only backends with an implemented module are actively assessed; others are "
        "reported as discovered but not assessed.",
        "A completed assessment means the process finished — not that the application is secure.",
        "Absence of findings is not evidence of security.",
    ]

    return {
        "report_version": 1,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "executive_summary": {
            "application": artifact.package_identifier if artifact else None,
            "artifact_filename": artifact.filename if artifact else None,
            "artifact_sha256": artifact.sha256 if artifact else None,
            "assessment_id": assessment_id,
            "assessment_status": assessment.status,
            "assessment_date": assessment.created_at.isoformat() if assessment.created_at else None,
            "scope": scope,
            "confirmed_findings": len(confirmed),
            "total_findings": len(findings),
        },
        "findings": [
            {
                "id": f.id,
                "title": f.title,
                "severity": f.severity,
                "status": f.status,
                "confidence": f.confidence,
                "evidence_quality": f.evidence_quality,
                "affected_resource": f.affected_resource,
                "impact": f.impact,
                "remediation": f.remediation,
                "evidence": json.loads(f.evidence_json) if f.evidence_json else None,
                "reproduction": _reproduction(f),
            }
            for f in findings
        ],
        "coverage": coverage,
        "limitations": limitations,
    }


def _arg(execution: ToolExecution, key: str) -> str | None:
    try:
        return json.loads(execution.arguments_json or "{}").get(key)
    except json.JSONDecodeError:
        return None


def _reproduction(f: Finding) -> str:
    return (
        f"As an unauthenticated client, issue a minimal read against {f.affected_resource} "
        "using the application's public client key; observe that rows are returned."
    )
