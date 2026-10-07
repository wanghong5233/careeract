"""Reserve the single Steel instance before lifecycle side effects."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_steel_operations"
down_revision: str | None = "0017_boss_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "steel_operations",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint("slot = 1", name="steel_single_instance"),
        sa.CheckConstraint(
            "state IN ('creating','live','releasing','released')", name="steel_operation_state"
        ),
        schema="browser",
    )
    op.create_index(
        "steel_operation_active_slot",
        "steel_operations",
        ["slot"],
        unique=True,
        postgresql_where=sa.text("state <> 'released'"),
        schema="browser",
    )


def downgrade() -> None:
    op.drop_index("steel_operation_active_slot", table_name="steel_operations", schema="browser")
    op.drop_table("steel_operations", schema="browser")
