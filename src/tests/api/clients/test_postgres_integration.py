import pytest
from collections.abc import Generator
import os
from dotenv import load_dotenv

from api.clients.postgres_sql_client import (
    PostgresSQLClient,
    DatabaseConfig,
    DatabaseError,
)

load_dotenv()


@pytest.fixture(scope="session")
def db_config() -> DatabaseConfig:
    return DatabaseConfig(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        username="test_user",
        password="test_password",  # pragma: allowlist secret
        database="test_db",
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


@pytest.fixture(scope="function")
def test_procedure(
    db_client: PostgresSQLClient, test_table: str
) -> Generator[str, None, None]:
    """Create a test stored procedure."""
    proc_name = "get_users_by_age"

    # Create stored procedure
    create_proc = f"""
    CREATE OR REPLACE FUNCTION {proc_name}(min_age INTEGER)
    RETURNS TABLE(name VARCHAR, email VARCHAR, age INTEGER)
    AS $$
    BEGIN
        RETURN QUERY
        SELECT t.name, t.email, t.age
        FROM {test_table} t
        WHERE t.age >= min_age;
    END;
    $$ LANGUAGE plpgsql;
    """
    db_client.execute_command(create_proc)

    yield proc_name

    # Cleanup
    db_client.execute_command(f"DROP FUNCTION IF EXISTS {proc_name}(INTEGER)")


@pytest.fixture()
def sample_data() -> list[dict]:
    return [
        {"name": "Alice Johnson", "email": "alice@example.com", "age": 30},
        {"name": "Bob Smith", "email": "bob@example.com", "age": 25},
        {"name": "Charlie Brown", "email": "charlie@example.com", "age": 35},
    ]


# ============================================
# CONNECTION POOL TESTS
# ============================================


class TestConnectionPool:
    """Test connection pooling functionality."""

    def test_pool_initialization(self, db_client: PostgresSQLClient):
        """Test that the connection pool is properly initialized."""
        # The pool should exist after initialization
        assert db_client._pool is not None
        assert db_client._pool.closed == 0  # 0 means pool is open

    def test_get_connection(self, db_client: PostgresSQLClient):
        """Test getting a connection from the pool."""
        with db_client.get_connection() as conn:
            # Connection should be valid
            assert conn is not None
            assert conn.closed == 0  # 0 means connection is open

            # Test that we can execute a simple query
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                assert result[0] == 1

    def test_connection_returned_to_pool(self, db_client: PostgresSQLClient):
        """Test that connections are properly returned to the pool."""
        initial_conn = None

        # Get a connection and store its id
        with db_client.get_connection() as conn:
            initial_conn = id(conn)

        # Get another connection - might be the same one if pool reuses
        with db_client.get_connection() as conn:
            # This test verifies the connection is valid
            assert conn is not None
            assert conn.closed == 0
            assert id(conn) == initial_conn


# ============================================
# QUERY EXECUTION TESTS
# ============================================


class TestQueryExecution:
    """Test query execution methods."""

    def test_execute_query_fetch_all(
        self, db_client: PostgresSQLClient, test_table: str, sample_data: list
    ):
        """Test executing SELECT query with fetch all."""
        # Insert test data
        for data in sample_data:
            query = f"INSERT INTO {test_table} (name, email, age) VALUES (%(name)s, %(email)s, %(age)s)"
            db_client.execute_command(query, data)

        # Test fetch all
        select_query = f"SELECT * FROM {test_table} ORDER BY name"
        results = db_client.execute_query(select_query, fetch="all")

        assert results is not None
        assert len(results) == 3
        assert results[0]["name"] == "Alice Johnson"
        assert all(isinstance(row, dict) for row in results)

    def test_execute_query_fetch_one(
        self, db_client: PostgresSQLClient, test_table: str, sample_data: list
    ):
        """Test executing SELECT query with fetch one."""
        # Insert one record
        data = sample_data[0]
        query = f"INSERT INTO {test_table} (name, email, age) VALUES (%(name)s, %(email)s, %(age)s)"
        db_client.execute_command(query, data)

        # Test fetch one
        select_query = f"SELECT * FROM {test_table} WHERE email = %(email)s"
        result = db_client.execute_query(
            select_query, {"email": "alice@example.com"}, fetch="one"
        )

        assert result is not None
        assert len(result) == 1
        assert result[0]["email"] == "alice@example.com"

    def test_execute_query_with_params(
        self, db_client: PostgresSQLClient, test_table: str, sample_data: list
    ):
        """Test query execution with parameters (prevents SQL injection)."""
        # Insert test data
        for data in sample_data:
            query = f"INSERT INTO {test_table} (name, email, age) VALUES (%(name)s, %(email)s, %(age)s)"
            db_client.execute_command(query, data)

        # Test with tuple params
        query_tuple = f"SELECT * FROM {test_table} WHERE age > %s"
        results = db_client.execute_query(query_tuple, (28,))
        assert len(results) == 2  # Alice (30) and Charlie (35)

        # Test with dict params
        query_dict = f"SELECT * FROM {test_table} WHERE age > %(min_age)s"
        results = db_client.execute_query(query_dict, {"min_age": 28})
        assert len(results) == 2

    def test_execute_query_no_results(
        self, db_client: PostgresSQLClient, test_table: str
    ):
        """Test query that returns no results."""
        query = f"SELECT * FROM {test_table} WHERE age > 100"
        results = db_client.execute_query(query)

        assert results == []

    def test_invalid_fetch_mode(self, db_client: PostgresSQLClient, test_table: str):
        """Test that invalid fetch mode raises ValueError."""
        query = f"SELECT * FROM {test_table}"

        with pytest.raises(
            ValueError, match="Fetch mode must be either 'all' or 'one'"
        ):
            db_client.execute_query(query, fetch="invalid")


# ============================================
# COMMAND EXECUTION TESTS
# ============================================


class TestCommandExecution:
    """Test command execution methods (INSERT, UPDATE, DELETE)."""

    def test_execute_command_insert(
        self, db_client: PostgresSQLClient, test_table: str
    ):
        """Test INSERT command."""
        query = f"INSERT INTO {test_table} (name, email, age) VALUES (%s, %s, %s)"
        affected_rows = db_client.execute_command(
            query, ("John Doe", "john@example.com", 28)
        )

        assert affected_rows == 1

        # Verify data was inserted
        select_query = f"SELECT * FROM {test_table} WHERE email = 'john@example.com'"
        result = db_client.execute_query(select_query)
        assert len(result) == 1
        assert result[0]["name"] == "John Doe"

    def test_execute_command_update(
        self, db_client: PostgresSQLClient, test_table: str, sample_data: list
    ):
        """Test UPDATE command."""
        # Insert initial data
        data = sample_data[0]
        insert_query = f"INSERT INTO {test_table} (name, email, age) VALUES (%(name)s, %(email)s, %(age)s)"
        db_client.execute_command(insert_query, data)

        # Update the record
        update_query = f"UPDATE {test_table} SET age = %s WHERE email = %s"
        affected_rows = db_client.execute_command(
            update_query, (31, "alice@example.com")
        )

        assert affected_rows == 1

        # Verify update
        result = db_client.execute_query(
            f"SELECT age FROM {test_table} WHERE email = 'alice@example.com'"
        )
        assert result[0]["age"] == 31

    def test_execute_command_delete(
        self, db_client: PostgresSQLClient, test_table: str, sample_data: list
    ):
        """Test DELETE command."""
        # Insert multiple records
        for data in sample_data:
            query = f"INSERT INTO {test_table} (name, email, age) VALUES (%(name)s, %(email)s, %(age)s)"
            db_client.execute_command(query, data)

        # Delete records with age > 30
        delete_query = f"DELETE FROM {test_table} WHERE age > %s"
        affected_rows = db_client.execute_command(delete_query, (30,))

        assert affected_rows == 1  # Only Charlie (35) should be deleted

        # Verify deletion
        remaining = db_client.execute_query(f"SELECT * FROM {test_table}")
        assert len(remaining) == 2

    def test_execute_many(
        self, db_client: PostgresSQLClient, test_table: str, sample_data: list
    ):
        """Test bulk insert with execute_many."""
        query = f"INSERT INTO {test_table} (name, email, age) VALUES (%s, %s, %s)"

        # Prepare data as list of tuples
        params_list = [(d["name"], d["email"], d["age"]) for d in sample_data]

        affected_rows = db_client.execute_many(query, params_list)
        assert affected_rows == 3

        # Verify all records were inserted
        results = db_client.execute_query(f"SELECT * FROM {test_table}")
        assert len(results) == 3


# ============================================
# TRANSACTION TESTS
# ============================================


class TestTransactions:
    """Test transaction handling."""

    def test_successful_transaction(
        self, db_client: PostgresSQLClient, test_table: str
    ):
        """Test that successful transactions are committed."""
        with db_client.transaction() as conn:
            with conn.cursor() as cursor:
                # Insert two records in a transaction
                cursor.execute(
                    f"INSERT INTO {test_table} (name, email, age) VALUES (%s, %s, %s)",
                    ("User 1", "user1@example.com", 25),
                )
                cursor.execute(
                    f"INSERT INTO {test_table} (name, email, age) VALUES (%s, %s, %s)",
                    ("User 2", "user2@example.com", 30),
                )

        # Verify both records were committed
        results = db_client.execute_query(f"SELECT * FROM {test_table}")
        assert len(results) == 2

    def test_failed_transaction_rollback(
        self, db_client: PostgresSQLClient, test_table: str
    ):
        """Test that failed transactions are rolled back."""
        # Insert one valid record first
        db_client.execute_command(
            f"INSERT INTO {test_table} (name, email, age) VALUES (%s, %s, %s)",
            ("Valid User", "valid@example.com", 25),
        )

        # Try to insert duplicate email (should fail due to UNIQUE constraint)
        with pytest.raises(DatabaseError):
            with db_client.transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"INSERT INTO {test_table} (name, email, age) VALUES (%s, %s, %s)",
                        ("New User", "new@example.com", 30),
                    )
                    # This should fail due to unique constraint
                    cursor.execute(
                        f"INSERT INTO {test_table} (name, email, age) VALUES (%s, %s, %s)",
                        ("Duplicate", "valid@example.com", 35),
                    )

        # Verify only the first record exists (transaction was rolled back)
        results = db_client.execute_query(f"SELECT * FROM {test_table}")
        assert len(results) == 1
        assert results[0]["email"] == "valid@example.com"


# ============================================
# ERROR HANDLING TESTS
# ============================================


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_query_syntax(self, db_client: PostgresSQLClient):
        """Test handling of invalid SQL syntax."""
        with pytest.raises(DatabaseError):
            db_client.execute_query("SELECT * FROM non_existent_table")

    def test_connection_error_handling(self, db_config: DatabaseConfig):
        """Test handling of connection errors."""
        # Create config with wrong credentials
        bad_config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="wrong_db",
            username="wrong_user",
            password="wrong_password",  # pragma: allowlist secret
            timeout=5,
            min_connections=1,
            max_connections=2,
        )

        with pytest.raises(DatabaseError, match="Database pool initialization failed"):
            PostgresSQLClient(bad_config)

    def test_unique_constraint_violation(
        self, db_client: PostgresSQLClient, test_table: str
    ):
        """Test handling of unique constraint violations."""
        # Insert first record
        db_client.execute_command(
            f"INSERT INTO {test_table} (name, email, age) VALUES (%s, %s, %s)",
            ("User 1", "user@example.com", 25),
        )

        # Try to insert duplicate email
        with pytest.raises(DatabaseError):
            db_client.execute_command(
                f"INSERT INTO {test_table} (name, email, age) VALUES (%s, %s, %s)",
                ("User 2", "user@example.com", 30),
            )


# ============================================
# STORED PROCEDURE TESTS (Optional)
# ============================================


class TestStoredProcedures:
    """Test stored procedure functionality."""

    @pytest.fixture
    def test_procedure(
        self, db_client: PostgresSQLClient, test_table: str
    ) -> Generator[str, None, None]:
        """Create a test stored procedure."""
        proc_name = "get_users_by_age"

        # Create stored procedure
        create_proc = f"""
        CREATE OR REPLACE FUNCTION {proc_name}(min_age INTEGER)
        RETURNS TABLE(name VARCHAR, email VARCHAR, age INTEGER)
        AS $$
        BEGIN
            RETURN QUERY
            SELECT t.name, t.email, t.age
            FROM {test_table} t
            WHERE t.age >= min_age;
        END;
        $$ LANGUAGE plpgsql;
        """
        db_client.execute_command(create_proc)

        yield proc_name

        # Cleanup
        db_client.execute_command(f"DROP FUNCTION IF EXISTS {proc_name}(INTEGER)")

    def test_call_procedure(
        self,
        db_client: PostgresSQLClient,
        test_table: str,
        test_procedure: str,
        sample_data: list,
    ):
        """Test calling a stored procedure."""
        # Insert test data
        for data in sample_data:
            query = f"INSERT INTO {test_table} (name, email, age) VALUES (%(name)s, %(email)s, %(age)s)"
            db_client.execute_command(query, data)

        # Call procedure
        results = db_client.call_procedure(test_procedure, [30])

        assert results is not None
        assert len(results) == 2  # Alice (30) and Charlie (35)


# ============================================
# INTEGRATION TEST CONFIGURATION
# ============================================

if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
