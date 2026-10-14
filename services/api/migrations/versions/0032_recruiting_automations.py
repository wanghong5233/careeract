"""Bound recurring replies to an owned, revocable conversation delegation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_recruiting_automations"
down_revision: str | None = "0031_communication_sends"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recruiting_automations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("connection_version", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("conversation_ids", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="accepted"),
        sa.Column("stage", sa.Text(), nullable=False, server_default="read"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_flight", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("max_sends", sa.Integer(), nullable=False),
        sa.Column("sends_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.Text()),
        sa.Column("read_task_id", sa.Uuid()),
        sa.Column("reply_id", sa.Uuid()),
        sa.Column("send_task_id", sa.Uuid()),
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
        sa.ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["career.boss_connections.id", "career.boss_connections.user_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "user_id", name="recruiting_automation_owner"),
        sa.UniqueConstraint("user_id", "request_key", name="recruiting_automation_request"),
        sa.CheckConstraint(
            "status IN ('accepted','running','waiting','completed','cancelled','timed_out')",
            name="recruiting_automation_status",
        ),
        sa.CheckConstraint("stage IN ('read','judge','send')", name="recruiting_automation_stage"),
        sa.CheckConstraint(
            "max_sends BETWEEN 1 AND 20 AND sends_reserved BETWEEN 0 AND max_sends "
            "AND interval_seconds BETWEEN 300 AND 3600 "
            "AND duration_minutes BETWEEN 1 AND 480 "
            "AND jsonb_array_length(conversation_ids) BETWEEN 1 AND 20",
            name="recruiting_automation_limits",
        ),
        schema="career",
    )
    op.create_index(
        "recruiting_automation_active",
        "recruiting_automations",
        ["connection_id", "user_id"],
        unique=True,
        schema="career",
        postgresql_where=sa.text("status IN ('accepted','running','waiting')"),
    )
    op.add_column("communication_sends", sa.Column("automation_id", sa.Uuid()), schema="career")
    op.create_foreign_key(
        "communication_send_automation",
        "communication_sends",
        "recruiting_automations",
        ["automation_id", "user_id"],
        ["id", "user_id"],
        source_schema="career",
        referent_schema="career",
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM career.recruiting_automations)")):
        raise RuntimeError("Preserve recruiting delegation evidence before downgrade")
    op.drop_constraint("communication_send_automation", "communication_sends", schema="career")
    op.drop_column("communication_sends", "automation_id", schema="career")
    op.drop_table("recruiting_automations", schema="career")
