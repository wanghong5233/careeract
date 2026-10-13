"""Persist bounded human control and fence old viewer credentials on handback."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_read_human_control"
down_revision: str | None = "0027_read_conversation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "execution_resources",
        sa.Column("human_control", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="career",
    )
    op.create_check_constraint(
        "read_human_target",
        "execution_resources",
        "NOT human_control OR (kind='boss_connection' AND conversation_id IS NOT NULL)",
        schema="career",
    )
    op.add_column(
        "sessions",
        sa.Column("viewer_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="browser",
    )


def downgrade() -> None:
    op.drop_column("sessions", "viewer_blocked", schema="browser")
    op.drop_constraint("read_human_target", "execution_resources", schema="career")
    op.drop_column("execution_resources", "human_control", schema="career")
