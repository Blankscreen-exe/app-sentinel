"""Live check for the Firebase RTDB open-rules module, against the mock Firebase lab.

Usage: python tests/live_firebase.py <broken|correct>   (run inside the worker)
"""

from __future__ import annotations

import json
import sys
import uuid

from app.agent.loop import run_assessment_loop
from app.db import SessionLocal
from app.llm.client import StubLLMClient
from app.models import ApplicationArtifact, Assessment, AttackSurfaceResource, Finding, Project

FB_URL = "http://firebase-lab:9000"
SCOPE = json.dumps({
    "active_testing_allowed": True,
    "authorized_hosts": ["firebase-lab"],
    "allow_lab_targets": True,
    "max_active_requests": 30,
})


def _planner():
    i = {"n": 0}

    def plan(system: str, prompt: str) -> dict:
        n = i["n"]; i["n"] += 1
        if n == 0:
            return {"objective": "probe RTDB", "action": "test_firebase_rtdb_read",
                    "arguments": {"base_url": FB_URL, "path": "/users"},
                    "expected_observation": "data or denied", "rationale": "firebase db discovered"}
        return {"objective": "done", "action": "stop", "expected_observation": "n/a",
                "rationale": "done", "stop_reason": "complete"}

    return plan


def main() -> None:
    mode = sys.argv[1]
    session = SessionLocal()
    proj = Project(name=f"fb-{uuid.uuid4().hex[:6]}"); session.add(proj); session.flush()
    art = ApplicationArtifact(project_id=proj.id, filename="fb.apk", upload_status="uploaded",
                              sha256="0" * 64); session.add(art); session.flush()
    assess = Assessment(artifact_id=art.id, status="created", scope_configuration=SCOPE)
    session.add(assess); session.flush()
    session.add(AttackSurfaceResource(assessment_id=assess.id, resource_type="firebase_db",
                identifier=FB_URL, discovery_method="jadx-decompiled",
                authorization_status="unapproved"))
    session.commit()

    run_assessment_loop(session, assess.id, StubLLMClient(_planner()))
    findings = session.query(Finding).filter_by(assessment_id=assess.id).all()
    print(f"== mode={mode}: {len(findings)} finding(s) ==")
    for f in findings:
        print(f"  {f.title} [{f.severity}]")
    if mode == "broken":
        assert any("Firebase" in f.title for f in findings), "expected a Firebase open-read finding"
    else:
        assert not findings, "correct mode must yield no findings"
    print("FIREBASE CHECK PASSED")
    session.close()


if __name__ == "__main__":
    main()
