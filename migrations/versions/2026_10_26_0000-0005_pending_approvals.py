"""pending approvals

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One paused agent run per chat session, waiting for the patient's decision.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_approvals (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            chat_session_id UUID NOT NULL UNIQUE
                REFERENCES chat_sessions(id) ON DELETE CASCADE,
            run_state TEXT NOT NULL,
            user_item JSON NOT NULL,
            user_message_sequence INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pending_approvals")
