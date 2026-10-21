"""intake preferred_date replaces allergies

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21 17:41:04.881023

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE patient_intake_state ADD COLUMN IF NOT EXISTS preferred_date DATE"
    )
    op.execute("ALTER TABLE patient_intake_state DROP COLUMN IF EXISTS allergies")


def downgrade() -> None:
    op.execute("ALTER TABLE patient_intake_state DROP COLUMN IF EXISTS preferred_date")
