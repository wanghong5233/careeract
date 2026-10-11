"""Bind bounded read tasks to owned resources independently of login sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_read_execution_resources"
down_revision: str | None = "0022_saved_login_viewers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("execution_task_status", "execution_tasks", schema="career", type_="check")
    op.create_check_constraint(
        "execution_task_status",
        "execution_tasks",
        "status IN ('accepted','running','waiting','failed','timed_out','cancelled',"
        "'completed','unknown')",
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
        "'read_failed','read_unknown','browser_creating','browser_created',"
        "'creation_unconfirmed','creation_rejected','browser_released')",
        schema="career",
    )
    op.alter_column("execution_tasks", "connection_id", nullable=True, schema="career")
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
    op.create_unique_constraint(
        "material_owner_key", "materials", ["id", "user_id"], schema="career"
    )
    op.create_table(
        "execution_resources",
        sa.Column("task_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("connection_id", sa.Uuid()),
        sa.Column("connection_version", sa.Uuid()),
        sa.Column("material_id", sa.Uuid()),
        sa.Column("material_version_id", sa.Uuid()),
        sa.Column("material_version", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["career.execution_tasks.id", "career.execution_tasks.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["career.boss_connections.id", "career.boss_connections.user_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["material_id", "user_id"],
            ["career.materials.id", "career.materials.user_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["material_id", "material_version_id"],
            ["career.material_versions.material_id", "career.material_versions.id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint(
            "(kind='boss_connection' AND connection_id IS NOT NULL "
            "AND connection_version IS NOT NULL AND material_id IS NULL "
            "AND material_version_id IS NULL AND material_version IS NULL) OR "
            "(kind='material_version' AND material_id IS NOT NULL "
            "AND material_version_id IS NOT NULL AND material_version IS NOT NULL "
            "AND connection_id IS NULL AND connection_version IS NULL)",
            name="execution_resource_shape",
        ),
        schema="career",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM career.execution_tasks "
        "WHERE kind<>'boss_login') THEN "
        "RAISE EXCEPTION 'Read execution data must be retained before downgrade'; "
        "END IF; END $$"
    )
    op.drop_table("execution_resources", schema="career")
    op.drop_constraint(
        "execution_attempt_outcome", "execution_attempts", schema="career", type_="check"
    )
    op.create_check_constraint(
        "execution_attempt_outcome",
        "execution_attempts",
        "outcome IS NULL OR outcome IN ('browser_registered','registration_unconfirmed',"
        "'registration_rejected','cleanup_required','cancelled_before_start',"
        "'browser_creating','browser_created','creation_unconfirmed','creation_rejected',"
        "'browser_released')",
        schema="career",
    )
    op.drop_constraint("execution_task_status", "execution_tasks", schema="career", type_="check")
    op.create_check_constraint(
        "execution_task_status",
        "execution_tasks",
        "status IN ('accepted','running','waiting','failed','timed_out','cancelled','completed')",
        schema="career",
    )
    op.drop_constraint("material_owner_key", "materials", schema="career", type_="unique")
    op.drop_constraint(
        "execution_authorization_scope", "execution_authorizations", schema="career", type_="check"
    )
    op.create_check_constraint(
        "execution_authorization_scope",
        "execution_authorizations",
        "scope='boss.login'",
        schema="career",
    )
    op.drop_constraint("execution_task_kind", "execution_tasks", schema="career", type_="check")
    op.create_check_constraint(
        "execution_task_kind", "execution_tasks", "kind='boss_login'", schema="career"
    )
    op.alter_column("execution_tasks", "connection_id", nullable=False, schema="career")
