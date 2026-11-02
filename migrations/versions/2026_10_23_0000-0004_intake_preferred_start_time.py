"""intake preferred_start_time replaces preferred_slot

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE patient_intake_state ADD COLUMN IF NOT EXISTS preferred_start_time TIME"
    )
    # Existing values are read as UTC wall-clock time; the date is kept in preferred_date.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'patient_intake_state' AND column_name = 'preferred_slot'
            ) THEN
                UPDATE patient_intake_state
                SET preferred_start_time = (preferred_slot AT TIME ZONE 'UTC')::time,
                    preferred_date = COALESCE(
                        preferred_date, (preferred_slot AT TIME ZONE 'UTC')::date
                    )
                WHERE preferred_slot IS NOT NULL;
            END IF;
        END $$
        """
    )
    op.execute("ALTER TABLE patient_intake_state DROP COLUMN IF EXISTS preferred_slot")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE patient_intake_state ADD COLUMN IF NOT EXISTS preferred_slot TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        """
        UPDATE patient_intake_state
        SET preferred_slot = (preferred_date + preferred_start_time) AT TIME ZONE 'UTC'
        WHERE preferred_date IS NOT NULL AND preferred_start_time IS NOT NULL
        """
    )
    op.execute(
        "ALTER TABLE patient_intake_state DROP COLUMN IF EXISTS preferred_start_time"
    )
