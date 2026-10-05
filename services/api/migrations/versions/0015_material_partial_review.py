"""Persist precise proposal decisions without a second material version store."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0015_material_partial_review"
down_revision: str | None = "0014_conversation_branches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "material_proposals", sa.Column("changes", JSONB(), nullable=True), schema="career"
    )
    op.add_column(
        "material_proposals",
        sa.Column("review_version_id", sa.Uuid(), nullable=True),
        schema="career",
    )
    op.add_column(
        "material_proposals", sa.Column("review_version", sa.Uuid(), nullable=True), schema="career"
    )


def downgrade() -> None:
    for name in ("review_version", "review_version_id", "changes"):
        op.drop_column("material_proposals", name, schema="career")
