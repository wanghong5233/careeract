from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_conversation_title"
down_revision: str | None = "0010_conversation_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_work_sessions",
        sa.Column("title_origin", sa.Text(), nullable=False, server_default="manual"),
        schema="career",
    )
    op.add_column(
        "agent_work_sessions",
        sa.Column(
            "title_generation_attempted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        schema="career",
    )
    op.create_check_constraint(
        "conversation_title_origin",
        "agent_work_sessions",
        "title_origin IN ('default', 'manual', 'generated')",
        schema="career",
    )


def downgrade() -> None:
    op.drop_constraint(
        "conversation_title_origin", "agent_work_sessions", schema="career", type_="check"
    )
    op.drop_column("agent_work_sessions", "title_generation_attempted", schema="career")
    op.drop_column("agent_work_sessions", "title_origin", schema="career")
