"""unique appointment slot

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-02 00:00:00
"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One live appointment per doctor, date and start time. Cancelled and
    # no-show rows free the slot, matching the check in book_appointment().
    # The function's EXISTS check alone races under concurrent bookings; this
    # index makes the database reject the second insert.
    # Fails if existing rows already double-book a slot: cancel or remove the
    # duplicates first.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_appointments_doctor_slot
            ON appointments (doctor_id, appointment_date, start_time)
            WHERE status NOT IN ('cancelled', 'no_show')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_appointments_doctor_slot")
