from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_conversation_context"
down_revision: str | None = "0009_conversation_directory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_work_sessions",
        sa.Column(
            "context_version",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        schema="career",
    )


def downgrade() -> None:
    op.drop_column("agent_work_sessions", "context_version", schema="career")
