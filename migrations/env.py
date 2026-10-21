import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine

load_dotenv()

config = context.config


def get_url() -> URL:
    # Set POSTGRES_MIGRATION_HOST to override the host when running from the host machine
    return URL.create(
        "postgresql+psycopg2",
        username=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_MIGRATION_HOST") or os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT") or 5432),
        database=os.getenv("POSTGRES_DATABASE"),
    )


def run_migrations_offline() -> None:
    context.configure(url=get_url(), literal_binds=True, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
