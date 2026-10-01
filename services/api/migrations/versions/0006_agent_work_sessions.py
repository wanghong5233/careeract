"""Bind opaque Agent sessions to a user and optional CareerAct project."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_agent_work_sessions"
down_revision: str | None = "0005_career_projects_legacy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_work_sessions",
        sa.Column("session_id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["career.career_projects.id"], ondelete="SET NULL"),
        schema="career",
    )
    op.create_index(
        "agent_work_sessions_user_updated_idx",
        "agent_work_sessions",
        ["user_id", "updated_at", "session_id"],
        schema="career",
    )


def downgrade() -> None:
    op.drop_index(
        "agent_work_sessions_user_updated_idx",
        table_name="agent_work_sessions",
        schema="career",
    )
    op.drop_table("agent_work_sessions", schema="career")
