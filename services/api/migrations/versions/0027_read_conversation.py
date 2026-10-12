"""Bind a BOSS read task to an explicitly selected conversation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_read_conversation"
down_revision: str | None = "0026_read_stop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "execution_resources", sa.Column("conversation_id", sa.String(200)), schema="career"
    )
    op.create_check_constraint(
        "read_conversation_target",
        "execution_resources",
        "conversation_id IS NULL OR (kind='boss_connection' "
        "AND conversation_id ~ '^[A-Za-z0-9_-]{1,200}$')",
        schema="career",
    )


def downgrade() -> None:
    op.drop_constraint(
        "read_conversation_target", "execution_resources", schema="career", type_="check"
    )
    op.drop_column("execution_resources", "conversation_id", schema="career")
