from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_conversation_model"
down_revision: str | None = "0011_conversation_title"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_work_sessions", sa.Column("model_id", sa.Text()), schema="career")


def downgrade() -> None:
    op.drop_column("agent_work_sessions", "model_id", schema="career")
