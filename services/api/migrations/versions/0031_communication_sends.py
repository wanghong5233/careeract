"""Authorize immutable text replies through the existing execution ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_communication_sends"
down_revision: str | None = "0030_communication_replies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "communication_reply_owner", "communication_replies", ["id", "user_id"], schema="career"
    )
    op.create_table(
        "communication_sends",
        sa.Column("task_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("reply_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("reply_version", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_message_id", sa.Text()),
        sa.Column("cleanup_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["career.execution_tasks.id", "career.execution_tasks.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reply_id", "user_id"],
            ["career.communication_replies.id", "career.communication_replies.user_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint("length(text) BETWEEN 1 AND 1000", name="communication_send_text"),
        schema="career",
    )
    op.drop_constraint("execution_task_kind", "execution_tasks", schema="career", type_="check")
    op.create_check_constraint(
        "execution_task_kind",
        "execution_tasks",
        "(kind='boss_login' AND connection_id IS NOT NULL) OR "
        "(kind IN ('boss_read','material_read','boss_reply') AND connection_id IS NULL)",
        schema="career",
    )
    op.drop_constraint(
        "execution_authorization_scope", "execution_authorizations", schema="career", type_="check"
    )
    op.create_check_constraint(
        "execution_authorization_scope",
        "execution_authorizations",
        "scope IN ('boss.login','boss.read','material.read','boss.reply')",
        schema="career",
    )
    # Keep earlier lifecycle/read outcomes; extend rather than rewrite their evidence.
    op.drop_constraint(
        "execution_attempt_outcome", "execution_attempts", schema="career", type_="check"
    )
    op.create_check_constraint(
        "execution_attempt_outcome",
        "execution_attempts",
        "outcome IS NULL OR outcome IN ('browser_registered','registration_unconfirmed',"
        "'registration_rejected','cleanup_required','cancelled_before_start','read_completed',"
        "'read_failed','read_unknown','browser_creating','browser_created','creation_unconfirmed',"
        "'creation_rejected','browser_released','read_stop_requested','cancelled_after_stop',"
        "'read_human_control','read_handback_started','send_preparing','send_attempted',"
        "'send_completed','send_failed','send_unknown')",
        schema="career",
    )


def downgrade() -> None:
    # Empty-schema rollback remains testable; populated ledgers need explicit preservation.
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM career.communication_sends)")):
        raise RuntimeError("Preserve communication send evidence before downgrade")
    op.drop_table("communication_sends", schema="career")
    op.drop_constraint("communication_reply_owner", "communication_replies", schema="career")
    op.drop_constraint("execution_task_kind", "execution_tasks", schema="career", type_="check")
    op.create_check_constraint(
        "execution_task_kind",
        "execution_tasks",
        "(kind='boss_login' AND connection_id IS NOT NULL) OR "
        "(kind IN ('boss_read','material_read') AND connection_id IS NULL)",
        schema="career",
    )
    op.drop_constraint(
        "execution_authorization_scope", "execution_authorizations", schema="career", type_="check"
    )
    op.create_check_constraint(
        "execution_authorization_scope",
        "execution_authorizations",
        "scope IN ('boss.login','boss.read','material.read')",
        schema="career",
    )
    op.drop_constraint(
        "execution_attempt_outcome", "execution_attempts", schema="career", type_="check"
    )
    op.create_check_constraint(
        "execution_attempt_outcome",
        "execution_attempts",
        "outcome IS NULL OR outcome IN ('browser_registered','registration_unconfirmed',"
        "'registration_rejected','cleanup_required','cancelled_before_start','read_completed',"
        "'read_failed','read_unknown','browser_creating','browser_created','creation_unconfirmed',"
        "'creation_rejected','browser_released','read_stop_requested','cancelled_after_stop',"
        "'read_human_control','read_handback_started')",
        schema="career",
    )
