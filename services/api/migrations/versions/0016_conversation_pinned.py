from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_conversation_pinned"
down_revision: str | None = "0015_material_partial_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_work_sessions",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="career",
    )


def downgrade() -> None:
    op.drop_column("agent_work_sessions", "pinned", schema="career")
