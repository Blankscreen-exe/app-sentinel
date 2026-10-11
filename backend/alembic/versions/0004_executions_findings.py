"""tool_execution + finding tables

Revision ID: 0004_executions_findings
Revises: 0003_attack_surface
Create Date: 2026-10-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_executions_findings"
down_revision: str | None = "0003_attack_surface"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_execution",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("assessment_id", sa.String(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("arguments_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("gate_code", sa.String(length=40), nullable=True),
        sa.Column("outcome", sa.String(length=30), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessment.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_tool_execution_assessment_id", "tool_execution", ["assessment_id"])

    op.create_table(
        "finding",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("assessment_id", sa.String(), nullable=False),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="candidate"),
        sa.Column("confidence", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("evidence_quality", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("affected_resource", sa.String(length=500), nullable=True),
        sa.Column("impact", sa.Text(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["tool_execution.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_finding_assessment_id", "finding", ["assessment_id"])


def downgrade() -> None:
    op.drop_index("ix_finding_assessment_id", table_name="finding")
    op.drop_table("finding")
    op.drop_index("ix_tool_execution_assessment_id", table_name="tool_execution")
    op.drop_table("tool_execution")
