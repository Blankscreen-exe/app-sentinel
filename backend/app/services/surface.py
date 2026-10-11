"""Build the attack-surface model from an artifact's static-analysis discoveries.

Maps discovery kinds to resource types. Every resource starts `unapproved`: being
discovered in the APK does not authorize testing it (ADR-001). De-duplicated per
assessment by (type, identifier).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AttackSurfaceResource, Discovery, StaticAnalysis

# discovery.kind -> attack-surface resource_type
_KIND_TO_TYPE = {
    "endpoint": "endpoint",
    "insecure_endpoint": "endpoint",
    "table_ref": "table",
    "bucket_ref": "bucket",
    "sdk": "sdk",
    "client_key": "key",
    "secret": "key",
    "jwt": "key",
}


def build_attack_surface(session: Session, assessment_id: str, artifact_id: str) -> int:
    """Create resources for an assessment from the artifact's discoveries. Returns count."""
    analysis = session.query(StaticAnalysis).filter_by(artifact_id=artifact_id).one_or_none()
    if analysis is None:
        return 0

    discoveries = session.query(Discovery).filter_by(analysis_id=analysis.id).all()

    existing = {
        (r.resource_type, r.identifier)
        for r in session.query(AttackSurfaceResource)
        .filter_by(assessment_id=assessment_id)
        .all()
    }

    created = 0
    for d in discoveries:
        rtype = _KIND_TO_TYPE.get(d.kind)
        if rtype is None:
            continue
        key = (rtype, d.name)
        if key in existing:
            continue
        existing.add(key)
        session.add(
            AttackSurfaceResource(
                assessment_id=assessment_id,
                resource_type=rtype,
                identifier=d.name,
                source_location=d.location,
                discovery_method=d.detection_method,
                confidence=d.confidence,
                state="discovered",
                authorization_status="unapproved",
            )
        )
        created += 1
    session.commit()
    return created
