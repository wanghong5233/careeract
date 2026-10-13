"""Allow durable human-control and handback execution outcomes."""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_read_handback_outcomes"
down_revision: str | None = "0028_read_human_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_OUTCOMES = (
    "'browser_registered','registration_unconfirmed','registration_rejected',"
    "'cleanup_required','cancelled_before_start','read_completed','read_failed',"
    "'read_unknown','browser_creating','browser_created','creation_unconfirmed',"
    "'creation_rejected','browser_released','read_stop_requested','cancelled_after_stop'"
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
        + ",'read_human_control','read_handback_started')",
        schema="career",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE career.execution_attempts SET outcome='read_unknown', status='unknown' "
        "WHERE outcome IN ('read_human_control','read_handback_started')"
    )
    op.execute(
        "UPDATE career.execution_tasks SET status='unknown' WHERE id IN "
        "(SELECT task_id FROM career.execution_attempts WHERE outcome='read_unknown' "
        "AND status='unknown')"
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
