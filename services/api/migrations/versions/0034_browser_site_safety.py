"""Persist account/site risk stops independently of tasks and browser sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_browser_site_safety"
down_revision: str | None = "0033_boss_material_inspection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "site_safety",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("site", sa.String(64), primary_key=True),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text()),
        sa.Column("session_id", sa.Uuid()),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(NOT blocked AND reason IS NULL AND session_id IS NULL AND stopped_at IS NULL) OR "
            "(blocked AND reason IS NOT NULL "
            "AND reason IN ('denied', 'challenge', 'rate_limited', 'abnormal') "
            "AND session_id IS NOT NULL AND stopped_at IS NOT NULL)",
            name="complete_site_safety_stop",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["browser.sessions.session_id"]),
        schema="browser",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM browser.site_safety WHERE blocked)")
    ):
        raise RuntimeError("Preserve account protection evidence before downgrade")
    op.drop_table("site_safety", schema="browser")
