"""Attack-surface model: resources the app appears to interact with (assessment-level).

A resource is a discovered thing (a table, endpoint, bucket). It starts **unapproved**:
discovery does not authorize testing it. Provenance links it back to where it was found.
These represent discovered relationships, not verified vulnerabilities.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class AttackSurfaceResource(Base):
    __tablename__ = "attack_surface_resource"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id", "resource_type", "identifier", name="uq_resource_identity"
        ),
    )

    id: Mapped[str] = uuid_pk()
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessment.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # table | endpoint | bucket | sdk | key
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    identifier: Mapped[str] = mapped_column(String(500), nullable=False)
    source_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    discovery_method: Mapped[str] = mapped_column(String(60), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    # discovered (inferred) vs verified — set as checks confirm reachability/behaviour.
    state: Mapped[str] = mapped_column(String(20), default="discovered", nullable=False)
    # unapproved until explicitly added to scope. Discovery != authorization.
    authorization_status: Mapped[str] = mapped_column(
        String(20), default="unapproved", nullable=False
    )
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = created_at_col()
