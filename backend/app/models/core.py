"""First tables for the foundation.

Deliberately minimal (ADR-006): just enough to be real. The remaining entities
from the data model arrive with the features that need them.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col, uuid_pk


class Project(Base):
    __tablename__ = "project"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = created_at_col()

    artifacts: Mapped[list[ApplicationArtifact]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ApplicationArtifact(Base):
    __tablename__ = "application_artifact"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Original filename is kept only as data; files are stored under internal keys (ADR-004c).
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    internal_storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    platform: Mapped[str] = mapped_column(String(20), default="android", nullable=False)
    package_identifier: Mapped[str | None] = mapped_column(String(300), nullable=True)
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    upload_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    created_at: Mapped[dt.datetime] = created_at_col()

    project: Mapped[Project] = relationship(back_populates="artifacts")
    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )


class Assessment(Base):
    __tablename__ = "assessment"

    id: Mapped[str] = uuid_pk()
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("application_artifact.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Scope/permission configuration lives here as JSON for now (ADR-012: per-assessment overrides).
    scope_configuration: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="created", nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = created_at_col()

    artifact: Mapped[ApplicationArtifact] = relationship(back_populates="assessments")


class Setting(Base):
    """UI-editable key/value tunables (ADR-012). Limits only, never authorization."""

    __tablename__ = "setting"
    __table_args__ = (UniqueConstraint("key", name="uq_setting_key"),)

    id: Mapped[str] = uuid_pk()
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[dt.datetime] = created_at_col()
