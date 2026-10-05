from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0013_temporary_side_chat"
down_revision: str | None = "0012_conversation_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_work_sessions",
        sa.Column("temporary_until", sa.DateTime(timezone=True)),
        schema="career",
    )
    op.add_column("agent_work_sessions", sa.Column("side_context", JSONB()), schema="career")
    op.create_index(
        "side_chat_tab",
        "agent_work_sessions",
        ["user_id", sa.text("(side_context->>'tab_id')")],
        unique=True,
        schema="career",
        postgresql_where=sa.text("temporary_until IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("side_chat_tab", table_name="agent_work_sessions", schema="career")
    op.drop_column("agent_work_sessions", "side_context", schema="career")
    op.drop_column("agent_work_sessions", "temporary_until", schema="career")
