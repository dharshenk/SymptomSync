import pytest
from collections.abc import Generator

from src.api.clients.postgres_sql_client import PostgresSQLClient, DatabaseConfig


@pytest.fixture(scope="session")
def db_config() -> DatabaseConfig:
    return DatabaseConfig(
        host="localhost",
        port=5432,
        username="test_user",
        password="test_password",  # pragma: allowlist secret
        database="test_database",
        timeout=30,
        min_connections=1,
        max_connections=5,
        connect_timeout=10,
        command_timeout=30,
    )


@pytest.fixture(scope="session")
def db_client(db_config: DatabaseConfig) -> Generator[PostgresSQLClient, None, None]:
    client = PostgresSQLClient(db_config)
    yield client

    client.close()


@pytest.fixture(scope="function")
def test_table(db_client: PostgresSQLClient) -> Generator[str, None, None]:

    table_name = "test_users"

    # Setup: Create test table
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        age INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    db_client.execute_command(create_table_query)

    yield table_name

    # Teardown: Drop the table after test completes
    drop_table_query = f"DROP TABLE IF EXISTS {table_name}"
    db_client.execute_command(drop_table_query)


def sample_data() -> list[dict]:
    return [
        {"name": "Alice Johnson", "email": "alice@example.com", "age": 30},
        {"name": "Bob Smith", "email": "bob@example.com", "age": 25},
        {"name": "Charlie Brown", "email": "charlie@example.com", "age": 35},
    ]
