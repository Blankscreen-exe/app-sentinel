"""Run one comprehensive assessment against the lab (current mode) and print findings.

Used by the evaluation harness. Seeds an assessment whose attack surface covers all the
lab's candidate tables, runs the agent loop with a deterministic planner that tests every
table (full coverage), and prints the set of tables flagged as findings, as JSON.

Deterministic by design (stub planner) so precision/recall are repeatable. Run inside the
worker (reachable to main-db and lab-rest).
"""

from __future__ import annotations

import json
import sys
import uuid

from app.agent.loop import run_assessment_loop
from app.db import SessionLocal
from app.llm.client import StubLLMClient
from app.models import ApplicationArtifact, Assessment, AttackSurfaceResource, Finding, Project

LAB_URL = "http://lab-rest:3000"
CANDIDATE_TABLES = ["trips", "invoices", "profiles", "receipts"]
SCOPE = json.dumps({
    "active_testing_allowed": True,
    "authorized_hosts": ["lab-rest"],
    "authorized_resources": [f"table:{t}" for t in CANDIDATE_TABLES],
    "allow_lab_targets": True,
    "max_active_requests": 30,
})


def _planner():
    i = {"n": 0}

    def plan(system: str, prompt: str) -> dict:
        n = i["n"]; i["n"] += 1
        if n < len(CANDIDATE_TABLES):
            return {
                "objective": f"test {CANDIDATE_TABLES[n]}",
                "action": "test_scoped_anonymous_read",
                "arguments": {"base_url": LAB_URL, "table": CANDIDATE_TABLES[n]},
                "expected_observation": "rows or denial",
                "rationale": "coverage",
            }
        return {"objective": "done", "action": "stop", "expected_observation": "n/a",
                "rationale": "done", "stop_reason": "coverage complete"}

    return plan


def main() -> None:
    anon_key = sys.argv[1]
    session = SessionLocal()
    proj = Project(name=f"eval-{uuid.uuid4().hex[:6]}"); session.add(proj); session.flush()
    art = ApplicationArtifact(project_id=proj.id, filename="lab.apk", upload_status="uploaded",
                              sha256="0" * 64); session.add(art); session.flush()
    assess = Assessment(artifact_id=art.id, status="created", scope_configuration=SCOPE)
    session.add(assess); session.flush()
    for rtype, ident in [("endpoint", LAB_URL), ("key", anon_key)] + [
        ("table", t) for t in CANDIDATE_TABLES
    ]:
        session.add(AttackSurfaceResource(
            assessment_id=assess.id, resource_type=rtype, identifier=ident,
            discovery_method="content-scan", authorization_status="unapproved"))
    session.commit()

    run_assessment_loop(session, assess.id, StubLLMClient(_planner()))
    findings = session.query(Finding).filter_by(assessment_id=assess.id).all()
    flagged = sorted({f.affected_resource.split("/")[-1] for f in findings})
    print(json.dumps({"flagged": flagged}))
    session.close()


if __name__ == "__main__":
    main()
