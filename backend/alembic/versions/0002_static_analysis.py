"""static analysis + discovery tables

Revision ID: 0002_static_analysis
Revises: 0001_initial
Create Date: 2026-10-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_static_analysis"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "static_analysis",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("manifest_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["application_artifact.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("artifact_id", name="uq_static_analysis_artifact"),
    )
    op.create_index("ix_static_analysis_artifact_id", "static_analysis", ["artifact_id"])

    op.create_table(
        "discovery",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("analysis_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=400), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("detection_method", sa.String(length=60), nullable=False),
        sa.Column("confidence", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("severity_hint", sa.String(length=10), nullable=True),
        sa.Column(
            "needs_runtime_validation", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["static_analysis.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_discovery_analysis_id", "discovery", ["analysis_id"])


def downgrade() -> None:
    op.drop_index("ix_discovery_analysis_id", table_name="discovery")
    op.drop_table("discovery")
    op.drop_index("ix_static_analysis_artifact_id", table_name="static_analysis")
    op.drop_table("static_analysis")
