from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_conversation_directory"
down_revision: str | None = "0008_materials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_work_sessions",
        sa.Column("title", sa.Text(), nullable=False, server_default="历史对话"),
        schema="career",
    )
    op.add_column(
        "agent_work_sessions",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="career",
    )
    op.add_column(
        "agent_work_sessions",
        sa.Column(
            "version", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        schema="career",
    )
    op.create_index(
        "agent_work_sessions_user_created_idx",
        "agent_work_sessions",
        ["user_id", "created_at", "session_id"],
        schema="career",
    )


def downgrade() -> None:
    op.drop_index(
        "agent_work_sessions_user_created_idx", table_name="agent_work_sessions", schema="career"
    )
    for column in ("version", "archived", "title"):
        op.drop_column("agent_work_sessions", column, schema="career")
