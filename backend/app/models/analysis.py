"""Static-analysis result tables (main-db).

`StaticAnalysis` is one row per artifact holding the overall status and the
normalized manifest facts. `Discovery` is one row per individual finding, each
carrying provenance (where it came from and how it was detected).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col, uuid_pk


class StaticAnalysis(Base):
    __tablename__ = "static_analysis"
    __table_args__ = (UniqueConstraint("artifact_id", name="uq_static_analysis_artifact"),)

    id: Mapped[str] = uuid_pk()
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("application_artifact.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # queued | analyzing | analyzed | failed
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    # Normalized manifest facts as JSON text (kept simple; small payload).
    manifest_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = created_at_col()
    completed_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)

    discoveries: Mapped[list[Discovery]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class Discovery(Base):
    """One discovered fact, with provenance. Never a confirmed vulnerability by itself."""

    __tablename__ = "discovery"

    id: Mapped[str] = uuid_pk()
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("static_analysis.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # e.g. permission | exported_component | manifest_flag | endpoint | embedded_key | sdk
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(400), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provenance: where it was found and how.
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detection_method: Mapped[str] = mapped_column(String(60), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    # A neutral hint, not a verdict. Real findings require the agent + verification later.
    severity_hint: Mapped[str | None] = mapped_column(String(10), nullable=True)
    needs_runtime_validation: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[dt.datetime] = created_at_col()

    analysis: Mapped[StaticAnalysis] = relationship(back_populates="discoveries")
