"""Persist bounded read observations with their owned task."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_read_page_results"
down_revision: str | None = "0023_read_execution_resources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_read_results",
        sa.Column("task_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("page", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["career.execution_tasks.id", "career.execution_tasks.user_id"],
            ondelete="CASCADE",
        ),
        schema="career",
    )


def downgrade() -> None:
    op.drop_table("execution_read_results", schema="career")
