"""Preserve an older local career.projects table while creating the current project store."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_career_projects_legacy"
down_revision: str | None = "0004_career_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    legacy = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='career' AND table_name='projects' AND column_name='id'"
        )
    ).scalar_one_or_none()
    old_table = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='career' AND table_name='projects'"
        )
    ).scalar_one_or_none()
    if old_table is not None and legacy is None:
        op.rename_table("projects", "projects_legacy_0004", schema="career")

    exists = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='career' AND table_name='career_projects'"
        )
    ).scalar_one_or_none()
    if exists is None:
        op.create_table(
            "career_projects",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("purpose", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.Text(), nullable=False, server_default="planned"),
            sa.Column("version", sa.Uuid(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.CheckConstraint(
                "status IN ('planned', 'active', 'paused', 'completed', 'archived')",
                name="career_project_status",
            ),
            sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
            schema="career",
        )
        op.create_index(
            "career_projects_user_updated_idx",
            "career_projects",
            ["user_id", "updated_at", "id"],
            schema="career",
        )


def downgrade() -> None:
    connection = op.get_bind()
    legacy = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='career' AND table_name='projects_legacy_0004'"
        )
    ).scalar_one_or_none()
    current = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='career' AND table_name='projects'"
        )
    ).scalar_one_or_none()
    if legacy is not None and current is None:
        op.rename_table("projects_legacy_0004", "projects", schema="career")
