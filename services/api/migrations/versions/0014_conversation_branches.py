"""Add bounded branch provenance to agent work sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0014_conversation_branches"
down_revision: str | None = "0013_temporary_side_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_work_sessions",
        sa.Column("branch_context", JSONB(), nullable=True),
        schema="career",
    )


def downgrade() -> None:
    op.drop_column("agent_work_sessions", "branch_context", schema="career")
