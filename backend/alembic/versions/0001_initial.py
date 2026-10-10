"""initial foundation tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "application_artifact",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("internal_storage_key", sa.String(length=300), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=20), nullable=False, server_default="android"),
        sa.Column("package_identifier", sa.String(length=300), nullable=True),
        sa.Column("version", sa.String(length=100), nullable=True),
        sa.Column("upload_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_application_artifact_project_id", "application_artifact", ["project_id"]
    )

    op.create_table(
        "assessment",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("scope_configuration", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="created"),
        sa.Column("current_stage", sa.String(length=50), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["artifact_id"], ["application_artifact.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_assessment_artifact_id", "assessment", ["artifact_id"])

    op.create_table(
        "setting",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("key", name="uq_setting_key"),
    )


def downgrade() -> None:
    op.drop_table("setting")
    op.drop_index("ix_assessment_artifact_id", table_name="assessment")
    op.drop_table("assessment")
    op.drop_index("ix_application_artifact_project_id", table_name="application_artifact")
    op.drop_table("application_artifact")
    op.drop_table("project")
