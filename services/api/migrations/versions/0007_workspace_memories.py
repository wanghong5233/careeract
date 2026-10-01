"""Store user-owned career notes and rules with explicit lifecycle states."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_workspace_memories"
down_revision: str | None = "0006_agent_work_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_memories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="candidate"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="用户记录"),
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
        sa.CheckConstraint("kind IN ('note', 'rule')", name="workspace_memory_kind"),
        sa.CheckConstraint(
            "state IN ('candidate', 'confirmed', 'retired')", name="workspace_memory_state"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["career.career_projects.id"], ondelete="SET NULL"),
        schema="career",
    )
    op.create_index(
        "workspace_memories_user_updated_idx",
        "workspace_memories",
        ["user_id", "updated_at", "id"],
        schema="career",
    )


def downgrade() -> None:
    op.drop_index(
        "workspace_memories_user_updated_idx",
        table_name="workspace_memories",
        schema="career",
    )
    op.drop_table("workspace_memories", schema="career")
