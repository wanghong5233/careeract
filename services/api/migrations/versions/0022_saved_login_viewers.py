"""Track short lived read-only viewers restored from a saved browser login."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_saved_login_viewers"
down_revision: str | None = "0021_browser_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "boss_saved_login_viewers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("browser_session_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="starting"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('starting','live','closing','released','failed')",
            name="saved_login_viewer_status",
        ),
        sa.CheckConstraint("expires_at > created_at", name="saved_login_viewer_expiry"),
        schema="career",
    )
    op.create_index(
        "boss_saved_login_viewer_active",
        "boss_saved_login_viewers",
        ["connection_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('starting','live','closing')"),
        schema="career",
    )


def downgrade() -> None:
    op.drop_index(
        "boss_saved_login_viewer_active",
        table_name="boss_saved_login_viewers",
        schema="career",
    )
    op.drop_table("boss_saved_login_viewers", schema="career")
