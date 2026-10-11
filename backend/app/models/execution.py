"""Agent-run persistence: one row per step (audit) and the findings produced.

Every step is recorded whether it ran, was blocked by the gate, or failed — so an
assessment is fully auditable and a crash never looks like success.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class ToolExecution(Base):
    __tablename__ = "tool_execution"

    id: Mapped[str] = uuid_pk()
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessment.id", ondelete="CASCADE"), index=True, nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    arguments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ok | gate_denied | invalid_decision | tool_failed | stopped
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    gate_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)  # verifier outcome
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)       # LLM's stated reason
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = created_at_col()


class Finding(Base):
    __tablename__ = "finding"

    id: Mapped[str] = uuid_pk()
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessment.id", ondelete="CASCADE"), index=True, nullable=False
    )
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("tool_execution.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    # confirmed | candidate | inconclusive | false_positive | not_assessed
    status: Mapped[str] = mapped_column(String(20), default="candidate", nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    evidence_quality: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    affected_resource: Mapped[str | None] = mapped_column(String(500), nullable=True)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = created_at_col()
