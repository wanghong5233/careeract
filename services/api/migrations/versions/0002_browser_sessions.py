"""Persist browser ownership, leases and consumed commands."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_browser_sessions"
down_revision: str | None = "0001_auth_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema("browser", if_not_exists=True))
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lease_id", sa.Uuid()),
        sa.Column("owner_id", sa.Text()),
        sa.Column("attempt_id", sa.Uuid()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("draining", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "(lease_id IS NULL AND owner_id IS NULL AND attempt_id IS NULL "
            "AND expires_at IS NULL AND NOT draining) OR "
            "(lease_id IS NOT NULL AND owner_id IS NOT NULL AND attempt_id IS NOT NULL "
            "AND expires_at IS NOT NULL)",
            name="complete_lease",
        ),
        schema="browser",
    )
    op.create_table(
        "commands",
        sa.Column("command_id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["browser.sessions.session_id"]),
        schema="browser",
    )


def downgrade() -> None:
    op.drop_table("commands", schema="browser")
    op.drop_table("sessions", schema="browser")
    op.execute(sa.schema.DropSchema("browser"))
