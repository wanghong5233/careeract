"""Persist browser task, authorization, and attempt semantics."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_execution_semantics"
down_revision: str | None = "0019_browser_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "boss_connection_owner_key", "boss_connections", ["id", "user_id"], schema="career"
    )
    op.create_table(
        "execution_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="accepted"),
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
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["career.boss_connections.id", "career.boss_connections.user_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("connection_id", name="execution_task_connection_key"),
        sa.UniqueConstraint("user_id", "request_key", name="execution_task_request_key"),
        sa.UniqueConstraint("id", "user_id", name="execution_task_owner_key"),
        sa.CheckConstraint("kind='boss_login'", name="execution_task_kind"),
        sa.CheckConstraint(
            "status IN ('accepted','running','waiting','failed','timed_out',"
            "'cancelled','completed')",
            name="execution_task_status",
        ),
        schema="career",
    )
    op.create_table(
        "execution_authorizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["career.execution_tasks.id", "career.execution_tasks.user_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "task_id", "user_id", name="execution_authorization_owner_key"),
        sa.UniqueConstraint("task_id", name="execution_authorization_task_key"),
        sa.CheckConstraint("scope='boss.login'", name="execution_authorization_scope"),
        sa.CheckConstraint(
            "status IN ('active','revoked','expired')", name="execution_authorization_status"
        ),
        sa.CheckConstraint(
            "(status IN ('active','expired') AND revoked_at IS NULL) OR "
            "(status='revoked' AND revoked_at IS NOT NULL)",
            name="execution_authorization_revoked_at",
        ),
        schema="career",
    )
    op.create_table(
        "execution_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="accepted"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
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
        sa.Column("browser_session_id", sa.Uuid()),
        sa.Column("outcome", sa.Text()),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["career.execution_tasks.id", "career.execution_tasks.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id", "task_id", "user_id"],
            [
                "career.execution_authorizations.id",
                "career.execution_authorizations.task_id",
                "career.execution_authorizations.user_id",
            ],
            name="execution_attempt_authorization_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "request_id", name="execution_attempt_request_key"),
        sa.UniqueConstraint("task_id", name="execution_attempt_task_key"),
        sa.CheckConstraint(
            "status IN ('accepted','running','waiting','unknown','failed','cancelled','completed')",
            name="execution_attempt_status",
        ),
        sa.CheckConstraint(
            "(status='running' AND started_at IS NOT NULL) OR status <> 'running'",
            name="execution_attempt_started",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR status IN ('unknown','failed','cancelled','completed')",
            name="execution_attempt_finished",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('browser_registered','registration_unconfirmed',"
            "'registration_rejected','cleanup_required','cancelled_before_start')",
            name="execution_attempt_outcome",
        ),
        schema="career",
    )
    op.create_index(
        "execution_tasks_user_status",
        "execution_tasks",
        ["user_id", "status", "updated_at"],
        schema="career",
    )
    op.create_index(
        "execution_attempts_task", "execution_attempts", ["task_id", "created_at"], schema="career"
    )
    op.create_index(
        "execution_attempts_browser_session",
        "execution_attempts",
        ["browser_session_id"],
        unique=True,
        postgresql_where=sa.text("browser_session_id IS NOT NULL"),
        schema="career",
    )


def downgrade() -> None:
    op.drop_index("execution_attempts_task", table_name="execution_attempts", schema="career")
    op.drop_index(
        "execution_attempts_browser_session", table_name="execution_attempts", schema="career"
    )
    op.drop_index("execution_tasks_user_status", table_name="execution_tasks", schema="career")
    op.drop_table("execution_attempts", schema="career")
    op.drop_table("execution_authorizations", schema="career")
    op.drop_table("execution_tasks", schema="career")
    op.drop_constraint(
        "boss_connection_owner_key", "boss_connections", schema="career", type_="unique"
    )
