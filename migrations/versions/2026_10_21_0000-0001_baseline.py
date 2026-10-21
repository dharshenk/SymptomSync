"""baseline: frozen schema snapshot (migrations/sql/0001_baseline.sql)

Revision ID: 0001
Revises:
Create Date: 2026-10-21 00:00:00
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_SQL = Path(__file__).resolve().parents[1] / "sql" / "0001_baseline.sql"


def upgrade() -> None:
    # Not idempotent: for a DB that already has this schema, run `alembic stamp 0001` instead
    op.execute(BASELINE_SQL.read_text())


def downgrade() -> None:
    # Keep alembic_version: Alembic still needs to delete its own row afterwards
    op.execute(
        """
        DO $$
        DECLARE t text;
        BEGIN
            FOR t IN SELECT tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename <> 'alembic_version'
            LOOP
                EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', t);
            END LOOP;
        END $$;
        """
    )
