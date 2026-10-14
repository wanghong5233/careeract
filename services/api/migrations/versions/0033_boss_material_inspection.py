"""Bind platform material inspection to the existing read task and permission."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_boss_material_inspection"
down_revision: str | None = "0032_recruiting_automations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "execution_resources",
        sa.Column("inspect_resume", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="career",
    )
    op.create_check_constraint(
        "execution_resource_resume_inspection",
        "execution_resources",
        "NOT inspect_resume OR (kind='boss_connection' "
        "AND conversation_id IS NOT NULL AND NOT human_control)",
        schema="career",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM career.execution_resources WHERE inspect_resume)")
    ):
        raise RuntimeError("Preserve platform material inspection evidence before downgrade")
    op.drop_constraint(
        "execution_resource_resume_inspection", "execution_resources", schema="career"
    )
    op.drop_column("execution_resources", "inspect_resume", schema="career")
