"""Load the recorded demo assessment into the database for offline demos.

Inserts a completed assessment (steps + findings) from recorded_assessment.json, marked
RECORDED so the UI shows a banner. Needs only main-db + the API — no lab, no Claude, no
network. Idempotent: uses a fixed assessment id and replaces any prior load.

Run inside the worker/api container:
    docker compose exec worker python demo/load_recorded_demo.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

from app.db import SessionLocal
from app.models import (
    ApplicationArtifact,
    Assessment,
    AttackSurfaceResource,
    Finding,
    Project,
    ToolExecution,
)

FIXED_ASSESSMENT_ID = "recordeddemo0000000000000000demo"
FIXTURE = pathlib.Path(__file__).with_name("recorded_assessment.json")


def main() -> None:
    data = json.loads(FIXTURE.read_text())
    session = SessionLocal()
    try:
        # Idempotent: remove any prior recording.
        old = session.get(Assessment, FIXED_ASSESSMENT_ID)
        if old is not None:
            session.delete(old)
            session.commit()

        project = (
            session.query(Project).filter_by(name="Recorded demo").one_or_none()
            or Project(name="Recorded demo")
        )
        session.add(project)
        session.flush()

        artifact = ApplicationArtifact(
            project_id=project.id, filename="recorded-demo.apk", upload_status="uploaded",
            sha256="0" * 64, package_identifier=data.get("package"),
        )
        session.add(artifact)
        session.flush()

        assessment = Assessment(
            id=FIXED_ASSESSMENT_ID, artifact_id=artifact.id, status="completed",
            current_stage="recorded_demo",
            scope_configuration=json.dumps({"_recorded": True, "allow_lab_targets": True}),
            failure_reason=None,
        )
        session.add(assessment)
        session.flush()

        for r in data["resources"]:
            session.add(AttackSurfaceResource(
                assessment_id=assessment.id, resource_type=r["resource_type"],
                identifier=r["identifier"], discovery_method="content-scan",
                authorization_status="unapproved",
            ))

        base = dt.datetime(2026, 10, 11, 12, 0, 0, tzinfo=dt.UTC)
        step_exec_ids: dict[int, str] = {}
        for i, s in enumerate(data["steps"]):
            ex = ToolExecution(
                assessment_id=assessment.id, step_index=i, tool_name=s["tool"],
                arguments_json=s.get("arguments"), status=s["status"], outcome=s.get("outcome"),
                rationale=s.get("rationale"), detail=s.get("detail"),
                created_at=base + dt.timedelta(seconds=i * 17),
            )
            session.add(ex)
            session.flush()
            step_exec_ids[i] = ex.id

        for f in data["findings"]:
            session.add(Finding(
                assessment_id=assessment.id,
                execution_id=step_exec_ids.get(f.get("evidence_step", -1)),
                title=f["title"], severity=f["severity"], status=f["status"],
                confidence=f["confidence"], evidence_quality=f["evidence_quality"],
                affected_resource=f["affected_resource"], impact=f["impact"],
                remediation=f["remediation"],
                evidence_json=json.dumps({"recorded": True}),
            ))

        session.commit()
        print(f"loaded recorded demo: /assessments/{FIXED_ASSESSMENT_ID}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
