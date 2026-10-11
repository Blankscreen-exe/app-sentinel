"""Live end-to-end agent-loop check against the lab.

Drives the real loop (validate -> scope gate -> execute -> verify -> persist) with a
SCRIPTED stub planner (so no LLM credentials are needed), against the running lab.
Asserts findings per mode, and that an out-of-scope target is blocked.

Run inside the worker (reachable to main-db AND lab-rest):
    docker compose exec worker python tests/live_agent_check.py <anon_key> <broken|correct>
"""

from __future__ import annotations

import sys
import uuid

from app.db import SessionLocal
from app.llm.client import StubLLMClient
from app.models import (
    ApplicationArtifact,
    Assessment,
    AttackSurfaceResource,
    Finding,
    Project,
    ToolExecution,
)
from app.agent.loop import run_assessment_loop

LAB_URL = "http://lab-rest:3000"
SCOPE_IN = (
    '{"active_testing_allowed": true, "authorized_hosts": ["lab-rest"], '
    '"authorized_resources": ["table:trips", "table:invoices", "table:profiles"], '
    '"allow_lab_targets": true, "max_active_requests": 30}'
)
SCOPE_OUT = (
    '{"active_testing_allowed": true, "authorized_hosts": [], '
    '"allow_lab_targets": true, "max_active_requests": 30}'
)


def _seed(session, anon_key: str, scope_json: str) -> str:
    proj = Project(name=f"live-{uuid.uuid4().hex[:6]}")
    session.add(proj); session.flush()
    art = ApplicationArtifact(project_id=proj.id, filename="lab.apk", upload_status="uploaded",
                              sha256="0" * 64)
    session.add(art); session.flush()
    assess = Assessment(artifact_id=art.id, status="created", scope_configuration=scope_json)
    session.add(assess); session.flush()
    for rtype, ident in [
        ("endpoint", LAB_URL), ("table", "trips"), ("table", "invoices"),
        ("table", "profiles"), ("key", anon_key),
    ]:
        session.add(AttackSurfaceResource(
            assessment_id=assess.id, resource_type=rtype, identifier=ident,
            discovery_method="content-scan", authorization_status="unapproved",
        ))
    session.commit()
    return assess.id


def _scripted_planner():
    tables = ["trips", "invoices", "profiles"]
    state = {"i": 0}

    def plan(system: str, prompt: str) -> dict:
        i = state["i"]; state["i"] += 1
        if i < len(tables):
            return {
                "objective": f"test anon read of {tables[i]}",
                "action": "test_scoped_anonymous_read",
                "arguments": {"base_url": LAB_URL, "table": tables[i]},
                "expected_observation": "rows or denial",
                "rationale": "discovered public key + table ref suggest testing anon access",
            }
        return {"objective": "done", "action": "stop", "expected_observation": "n/a",
                "rationale": "all candidate tables checked", "stop_reason": "coverage complete"}

    return plan


def main() -> None:
    anon_key, mode = sys.argv[1], sys.argv[2]
    session = SessionLocal()

    # --- in-scope run against the lab ---
    aid = _seed(session, anon_key, SCOPE_IN)
    summary = run_assessment_loop(session, aid, StubLLMClient(_scripted_planner()))
    findings = session.query(Finding).filter_by(assessment_id=aid).all()
    execs = session.query(ToolExecution).filter_by(assessment_id=aid).order_by(
        ToolExecution.step_index).all()
    print(f"== mode={mode} in-scope: {len(execs)} steps, {len(findings)} findings ==")
    for e in execs:
        print(f"  step {e.step_index}: {e.tool_name} -> status={e.status} outcome={e.outcome}")
    for f in findings:
        print(f"  FINDING: {f.title} [{f.severity}/{f.status}]")

    flagged = {f.affected_resource.split("/")[-1] for f in findings}
    if mode == "broken":
        assert "trips" in flagged and "invoices" in flagged, flagged
        assert "profiles" not in flagged, "profiles must not be flagged (true negative)"
    else:
        assert not flagged, f"correct mode must yield no findings, got {flagged}"

    # --- out-of-scope run: gate must block, no findings ---
    aid2 = _seed(session, anon_key, SCOPE_OUT)
    run_assessment_loop(session, aid2, StubLLMClient(_scripted_planner()))
    f2 = session.query(Finding).filter_by(assessment_id=aid2).count()
    denied = session.query(ToolExecution).filter_by(
        assessment_id=aid2, status="gate_denied").count()
    print(f"== out-of-scope: {denied} gate-denied steps, {f2} findings ==")
    assert f2 == 0 and denied >= 1, (f2, denied)

    print("LIVE AGENT CHECK PASSED")
    session.close()


if __name__ == "__main__":
    main()
