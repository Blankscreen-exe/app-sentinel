"""attack surface resource table

Revision ID: 0003_attack_surface
Revises: 0002_static_analysis
Create Date: 2026-10-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_attack_surface"
down_revision: str | None = "0002_static_analysis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attack_surface_resource",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("assessment_id", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(length=30), nullable=False),
        sa.Column("identifier", sa.String(length=500), nullable=False),
        sa.Column("source_location", sa.String(length=500), nullable=True),
        sa.Column("discovery_method", sa.String(length=60), nullable=False),
        sa.Column("confidence", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="discovered"),
        sa.Column(
            "authorization_status", sa.String(length=20), nullable=False, server_default="unapproved"
        ),
        sa.Column("extra", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessment.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "assessment_id", "resource_type", "identifier", name="uq_resource_identity"
        ),
    )
    op.create_index(
        "ix_attack_surface_resource_assessment_id", "attack_surface_resource", ["assessment_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attack_surface_resource_assessment_id", table_name="attack_surface_resource"
    )
    op.drop_table("attack_surface_resource")
