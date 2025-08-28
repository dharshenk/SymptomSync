from dotenv import load_dotenv
from pydantic import BaseModel
import logging
import psycopg2
import psycopg2.pool
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor
from typing import Any
from psycopg2.extensions import connection as psycopg2_connection

load_dotenv()


class DatabaseConfig(BaseModel):
    """Database configuration Settings"""

    host: str
    port: int
    database: str
    username: str
    password: str
    timeout: int = 30
    min_connections: int = 1
    max_connections: int = 5
    connect_timeout: int = 10
    command_timeout: int = 30


class DatabaseError(Exception):
    """Custom database exception"""

    pass


class PostgresSQLClient:
    """
    Production-grade PostgreSQL client with connection pooling,
    transaction support, and proper resource management.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._pool = self._initialize_pool()

    def _initialize_pool(self):
        """Initialize connection pool"""
        try:
            conn_params = {
                "host": self.config.host,
                "port": self.config.port,
                "database": self.config.database,
                "user": self.config.username,
                "password": self.config.password,
                "connect_timeout": self.config.connect_timeout,
                "options": f"-c statement_timeout={self.config.command_timeout * 1000}",
            }
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=self.config.min_connections,
                maxconn=self.config.max_connections,
                **conn_params,
            )
            self.logger.info(
                f"Database pool initialized: {self.config.min_connections}-{self.config.max_connections} connections"
            )
            return _pool
        except Exception as e:
            self.logger.error(f"Failed to initialize database pool: {e}")
            raise DatabaseError(f"Database pool initialization failed: {e}")

    @contextmanager
    def get_connection(self):
        conn: psycopg2_connection | None = None

        try:
            conn = self._pool.getconn()
            yield conn

        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Database operation failed:{e}")
            raise DatabaseError(f"Database operation failed: {e}")

        finally:
            if conn:
                self._pool.putconn(conn)

    @contextmanager
    def transaction(self):
        try:
            with self.get_connection() as conn:
                yield conn
                conn.commit()
        except:
            if conn:
                conn.rollback()
            raise

    def execute_query(
        self,
        query: str,
        params: tuple | dict | None = None,
        fetch: str = "all",
    ) -> list[dict[str, Any]] | None:

        if fetch not in ("all", "one"):
            raise ValueError("Fetch mode must be either 'all' or 'one'")

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if fetch == "all":
                    return [dict(row) for row in cursor.fetchall()]
                elif fetch == "one":
                    row = cursor.fetchone()
                    return [dict(row)] if row else None
                return None

    def execute_command(self, query: str, params: tuple | dict | None = None) -> int:

        with self.transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.rowcount

    def execute_many(self, query: str, params_list: list[tuple | dict]) -> int:

        with self.transaction() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(query, params_list)
                return cursor.rowcount

    def call_procedure(
        self, proc_name: str, params: list | None = None
    ) -> list[Any] | None:
        """
        Call stored procedure.

        Args:
            proc_name: Procedure name
            params: Procedure parameters

        Returns:
            Procedure results
        """
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.callproc(proc_name, params or [])
                try:
                    return cursor.fetchall()
                except psycopg2.ProgrammingError:
                    return None

    def close(self):
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            self.logger.info("Database pool closed")
