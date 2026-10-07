"""Persist the product-level BOSS connection lifecycle."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_boss_connections"
down_revision: str | None = "0016_conversation_pinned"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "boss_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False, server_default="boss"),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Uuid(), nullable=False),
        sa.Column("browser_session_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("last_observed_url", sa.Text(), nullable=True),
        sa.Column("last_observed_state", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint("platform = 'boss'", name="boss_connection_platform"),
        sa.CheckConstraint(
            "status IN ('pending','waiting_for_login','waiting_for_verification',"
            "'connected','blocked','revoked','failed')",
            name="boss_connection_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status NOT IN ('waiting_for_login','waiting_for_verification','connected') "
            "OR browser_session_id IS NOT NULL",
            name="boss_connection_session_required",
        ),
        sa.UniqueConstraint("user_id", "request_key", name="boss_connection_request_key"),
        schema="career",
    )
    op.create_index(
        "boss_connections_user_updated_idx",
        "boss_connections",
        ["user_id", "created_at", "id"],
        schema="career",
    )
    op.create_index(
        "boss_connection_active_user",
        "boss_connections",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('revoked','failed')"),
        schema="career",
    )


def downgrade() -> None:
    op.drop_index("boss_connection_active_user", table_name="boss_connections", schema="career")
    op.drop_index(
        "boss_connections_user_updated_idx", table_name="boss_connections", schema="career"
    )
    op.drop_table("boss_connections", schema="career")
