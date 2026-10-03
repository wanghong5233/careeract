"""Store versioned user-owned materials and reviewable agent proposals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_materials"
down_revision: str | None = "0007_workspace_memories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="active"),
        sa.Column("current_version_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("state IN ('active', 'archived')", name="material_state"),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["career.career_projects.id"], ondelete="SET NULL"),
        schema="career",
    )
    op.create_table(
        "material_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("references", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint("source IN ('seed', 'user', 'agent')", name="material_version_source"),
        sa.CheckConstraint(
            "(number=0 AND source='seed' AND body='') OR "
            "(number>0 AND source<>'seed' AND length(body)>0)",
            name="material_version_content",
        ),
        sa.ForeignKeyConstraint(["material_id"], ["career.materials.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("material_id", "number", name="material_version_number"),
        sa.UniqueConstraint("material_id", "id", name="material_version_owner"),
        schema="career",
    )
    op.create_table(
        "material_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("base_version_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_body", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("references", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("state", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('pending', 'accepted', 'rejected')", name="material_proposal_state"
        ),
        sa.ForeignKeyConstraint(["material_id"], ["career.materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["material_id", "base_version_id"],
            ["career.material_versions.material_id", "career.material_versions.id"],
        ),
        schema="career",
    )
    op.create_foreign_key(
        "materials_current_version_fk",
        "materials",
        "material_versions",
        ["id", "current_version_id"],
        ["material_id", "id"],
        source_schema="career",
        referent_schema="career",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_index(
        "materials_user_updated_idx", "materials", ["user_id", "updated_at", "id"], schema="career"
    )
    op.create_index(
        "material_proposals_user_state_idx",
        "material_proposals",
        ["user_id", "state", "created_at"],
        schema="career",
    )


def downgrade() -> None:
    op.drop_index(
        "material_proposals_user_state_idx", table_name="material_proposals", schema="career"
    )
    op.drop_index("materials_user_updated_idx", table_name="materials", schema="career")
    op.drop_constraint(
        "materials_current_version_fk", "materials", schema="career", type_="foreignkey"
    )
    op.drop_table("material_proposals", schema="career")
    op.drop_table("material_versions", schema="career")
    op.drop_table("materials", schema="career")
