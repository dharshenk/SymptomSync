"""pending approval status

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-26 01:00:00
"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 'processing' while a decision is being applied, so the row stays visible
    # to handle_message and can't be claimed twice.
    op.execute(
        """
        ALTER TABLE pending_approvals
            ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMP WITH TIME ZONE
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE pending_approvals
            DROP COLUMN IF EXISTS claimed_at,
            DROP COLUMN IF EXISTS status
        """
    )
