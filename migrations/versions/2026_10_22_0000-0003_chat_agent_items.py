"""chat agent items

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # json (not jsonb) so replayed items are byte-identical for prompt caching
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_agent_items (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
            item_sequence INTEGER NOT NULL,
            item JSON NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, item_sequence)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_agent_items")
