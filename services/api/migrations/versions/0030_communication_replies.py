"""Persist source-bound recruiting decisions independently of chat and browser leases."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_communication_replies"
down_revision: str | None = "0029_read_handback_outcomes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "communication_replies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("read_task_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="accepted"),
        sa.Column("outcome", sa.Text()),
        sa.Column("source", postgresql.JSONB(), nullable=False),
        sa.Column("decision", postgresql.JSONB()),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["career.boss_connections.id", "career.boss_connections.user_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["read_task_id", "user_id"],
            ["career.execution_tasks.id", "career.execution_tasks.user_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("user_id", "request_key", name="communication_reply_request"),
        sa.CheckConstraint(
            "status IN ('accepted','running','waiting','completed',"
            "'failed','timed_out','cancelled')",
            name="communication_reply_status",
        ),
        sa.CheckConstraint(
            "(status='running' AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL) "
            "OR (status<>'running' AND claim_token IS NULL AND claim_expires_at IS NULL)",
            name="communication_reply_claim",
        ),
        schema="career",
    )
    op.create_index(
        "communication_reply_source_active",
        "communication_replies",
        ["user_id", "connection_id", "conversation_id", "message_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('accepted','running','waiting','completed')"),
        schema="career",
    )
    op.create_index(
        "communication_reply_connection",
        "communication_replies",
        ["user_id", "connection_id", "created_at", "id"],
        schema="career",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM career.communication_replies) THEN "
        "RAISE EXCEPTION 'Communication evidence must be retained before downgrade'; "
        "END IF; END $$"
    )
    op.drop_table("communication_replies", schema="career")
