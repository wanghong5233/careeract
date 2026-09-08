"""Create the Better Auth 1.7.3 schema.

Revision ID: 0001_auth_schema
Revises:
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_auth_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema("auth", if_not_exists=True))
    op.execute(sa.schema.CreateSchema("agno", if_not_exists=True))

    op.create_table(
        "user",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("emailVerified", sa.Boolean(), nullable=False),
        sa.Column("image", sa.Text()),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        schema="auth",
    )
    op.create_table(
        "session",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("expiresAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ipAddress", sa.Text()),
        sa.Column("userAgent", sa.Text()),
        sa.Column("userId", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["userId"], ["auth.user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
        schema="auth",
    )
    op.create_index("session_userId_idx", "session", ["userId"], schema="auth")
    op.create_table(
        "account",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("accountId", sa.Text(), nullable=False),
        sa.Column("providerId", sa.Text(), nullable=False),
        sa.Column("userId", sa.Text(), nullable=False),
        sa.Column("accessToken", sa.Text()),
        sa.Column("refreshToken", sa.Text()),
        sa.Column("idToken", sa.Text()),
        sa.Column("accessTokenExpiresAt", sa.DateTime(timezone=True)),
        sa.Column("refreshTokenExpiresAt", sa.DateTime(timezone=True)),
        sa.Column("scope", sa.Text()),
        sa.Column("password", sa.Text()),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["userId"], ["auth.user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="auth",
    )
    op.create_index("account_userId_idx", "account", ["userId"], schema="auth")
    op.create_table(
        "verification",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("expiresAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="auth",
    )
    op.create_index(
        "verification_identifier_idx",
        "verification",
        ["identifier"],
        schema="auth",
    )
    op.create_table(
        "jwks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("publicKey", sa.Text(), nullable=False),
        sa.Column("privateKey", sa.Text(), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expiresAt", sa.DateTime(timezone=True)),
        sa.Column("alg", sa.Text()),
        sa.Column("crv", sa.Text()),
        sa.PrimaryKeyConstraint("id"),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_table("jwks", schema="auth")
    op.drop_index("verification_identifier_idx", table_name="verification", schema="auth")
    op.drop_table("verification", schema="auth")
    op.drop_index("account_userId_idx", table_name="account", schema="auth")
    op.drop_table("account", schema="auth")
    op.drop_index("session_userId_idx", table_name="session", schema="auth")
    op.drop_table("session", schema="auth")
    op.drop_table("user", schema="auth")
    op.execute(sa.schema.DropSchema("auth"))
