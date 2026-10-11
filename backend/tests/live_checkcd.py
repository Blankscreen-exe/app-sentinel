"""Live check for Supabase Check C (authenticated tenant isolation) and Check D (admin
RLS metadata review), against the lab. Run inside the worker.

Usage: python tests/live_checkcd.py <anon_key> <auth_tenantA_jwt> <broken|correct>
"""

from __future__ import annotations

import json
import sys
import uuid

from app.agent.loop import run_assessment_loop
from app.db import SessionLocal
from app.llm.client import StubLLMClient
from app.models import ApplicationArtifact, Assessment, AttackSurfaceResource, Finding, Project, ToolExecution

LAB_URL = "http://lab-rest:3000"
TENANT_A = "11111111-1111-1111-1111-111111111111"
ADMIN_DSN = "postgresql://postgres:labsuper@lab-db:5432/postgres"


def _scope(auth_jwt: str) -> str:
    return json.dumps({
        "active_testing_allowed": True,
        "authorized_hosts": ["lab-rest"],
        "authorized_resources": ["table:trips"],
        "allow_lab_targets": True,
        "max_active_requests": 30,
        "authenticated_test_accounts": [{"jwt": auth_jwt, "tenant_id": TENANT_A, "label": "userA"}],
        "admin_dsn": ADMIN_DSN,
    })


def _planner():
    steps = [
        {"action": "test_scoped_anonymous_read", "arguments": {"base_url": LAB_URL, "table": "trips"}},
        {"action": "test_authenticated_tenant_isolation", "arguments": {"base_url": LAB_URL, "table": "trips"}},
        {"action": "review_rls_configuration", "arguments": {}},
    ]
    i = {"n": 0}

    def plan(system: str, prompt: str) -> dict:
        n = i["n"]; i["n"] += 1
        if n < len(steps):
            return {**steps[n], "objective": f"step {n}", "expected_observation": "x", "rationale": "coverage"}
        return {"objective": "done", "action": "stop", "expected_observation": "n/a",
                "rationale": "done", "stop_reason": "complete"}

    return plan


def main() -> None:
    anon_key, auth_jwt, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    session = SessionLocal()
    proj = Project(name=f"cd-{uuid.uuid4().hex[:6]}"); session.add(proj); session.flush()
    art = ApplicationArtifact(project_id=proj.id, filename="lab.apk", upload_status="uploaded",
                              sha256="0" * 64); session.add(art); session.flush()
    assess = Assessment(artifact_id=art.id, status="created", scope_configuration=_scope(auth_jwt))
    session.add(assess); session.flush()
    for rtype, ident in [("endpoint", LAB_URL), ("key", anon_key), ("table", "trips")]:
        session.add(AttackSurfaceResource(assessment_id=assess.id, resource_type=rtype,
                    identifier=ident, discovery_method="content-scan", authorization_status="unapproved"))
    session.commit()

    run_assessment_loop(session, assess.id, StubLLMClient(_planner()))
    execs = session.query(ToolExecution).filter_by(assessment_id=assess.id).order_by(
        ToolExecution.step_index).all()
    findings = session.query(Finding).filter_by(assessment_id=assess.id).all()
    print(f"== mode={mode} ==")
    for e in execs:
        print(f"  {e.tool_name} -> {e.status}/{e.outcome}")
    for f in findings:
        print(f"  FINDING: {f.title} [{f.severity}]")

    titles = " ".join(f.title for f in findings)
    if mode == "broken":
        assert "Cross-tenant" in titles, "expected cross-tenant finding in broken mode"
        assert "Row Level Security disabled on 'trips'" in titles, "expected RLS-disabled finding"
    else:
        assert "Cross-tenant" not in titles, "correct mode must not flag cross-tenant"
        assert "disabled" not in titles, "correct mode: RLS should be enabled"
    print("CHECK C/D PASSED")
    session.close()


if __name__ == "__main__":
    main()
