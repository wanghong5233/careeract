"""Preserve login history while binding each connection to its current login task."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_repeatable_login_tasks"
down_revision: str | None = "0024_read_page_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("boss_connections", sa.Column("login_task_id", sa.Uuid()), schema="career")
    op.execute(
        "UPDATE career.boss_connections c SET login_task_id=t.id "
        "FROM career.execution_tasks t WHERE t.connection_id=c.id AND t.user_id=c.user_id"
    )
    op.create_foreign_key(
        "boss_connection_login_owner",
        "boss_connections",
        "execution_tasks",
        ["login_task_id", "user_id"],
        ["id", "user_id"],
        source_schema="career",
        referent_schema="career",
    )
    op.drop_constraint(
        "execution_task_connection_key", "execution_tasks", type_="unique", schema="career"
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "execution_task_connection_key", "execution_tasks", ["connection_id"], schema="career"
    )
    op.drop_constraint(
        "boss_connection_login_owner", "boss_connections", type_="foreignkey", schema="career"
    )
    op.drop_column("boss_connections", "login_task_id", schema="career")
