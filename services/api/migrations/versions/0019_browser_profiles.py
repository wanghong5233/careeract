"""Store scoped browser contexts as authenticated ciphertext."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_browser_profiles"
down_revision: str | None = "0018_steel_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("site", sa.Text(), nullable=False),
        sa.Column("version", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary()),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
        sa.CheckConstraint("length(site) BETWEEN 1 AND 64", name="profile_site"),
        sa.CheckConstraint(
            "(revoked AND ciphertext IS NULL) OR "
            "(NOT revoked AND ciphertext IS NOT NULL "
            "AND octet_length(ciphertext) BETWEEN 29 AND 1048604)",
            name="profile_ciphertext",
        ),
        schema="browser",
    )
    op.create_index(
        "profile_active_user_site",
        "profiles",
        ["user_id", "site"],
        unique=True,
        postgresql_where=sa.text("revoked=false"),
        schema="browser",
    )


def downgrade() -> None:
    op.drop_index("profile_active_user_site", table_name="profiles", schema="browser")
    op.drop_table("profiles", schema="browser")
