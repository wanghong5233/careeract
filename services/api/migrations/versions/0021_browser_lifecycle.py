"""Persist physical browser lifecycle evidence."""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_browser_lifecycle"
down_revision: str | None = "0020_execution_semantics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_OUTCOMES = (
    "'browser_registered','registration_unconfirmed','registration_rejected',"
    "'cleanup_required','cancelled_before_start'"
)


def upgrade() -> None:
    op.drop_constraint(
        "execution_attempt_outcome", "execution_attempts", schema="career", type_="check"
    )
    op.create_check_constraint(
        "execution_attempt_outcome",
        "execution_attempts",
        "outcome IS NULL OR outcome IN ("
        + LEGACY_OUTCOMES
        + ",'browser_creating','browser_created','creation_unconfirmed',"
        "'creation_rejected','browser_released')",
        schema="career",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE career.execution_attempts SET outcome='cleanup_required' "
        "WHERE outcome IN ('browser_creating','browser_created','creation_unconfirmed',"
        "'creation_rejected','browser_released')"
    )
    op.drop_constraint(
        "execution_attempt_outcome", "execution_attempts", schema="career", type_="check"
    )
    op.create_check_constraint(
        "execution_attempt_outcome",
        "execution_attempts",
        "outcome IS NULL OR outcome IN (" + LEGACY_OUTCOMES + ")",
        schema="career",
    )
