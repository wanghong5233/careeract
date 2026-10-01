"""Store user-owned career projects with optimistic versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_career_projects"
down_revision: str | None = "0003_career_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
            name="project_status",
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
    op.drop_index("career_projects_user_updated_idx", table_name="career_projects", schema="career")
    op.drop_table("career_projects", schema="career")
