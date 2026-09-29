"""Store each user's confirmed career profile with conditional updates."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_career_profiles"
down_revision: str | None = "0002_browser_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema("career", if_not_exists=True))
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Uuid(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
        schema="career",
    )


def downgrade() -> None:
    op.drop_table("profiles", schema="career")
    op.execute(sa.schema.DropSchema("career"))
