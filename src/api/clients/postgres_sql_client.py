from dotenv import load_dotenv
from pydantic import BaseModel
import logging
import psycopg2
import psycopg2.pool
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor
from typing import Any
from psycopg2.extensions import connection as psycopg2_connection
from src.api.telemetry import db_operation_context, traced

load_dotenv()


def _db_span_name(operation: str):
    """Include the calling service operation without exposing its arguments."""

    def name(*args, **kwargs) -> str:
        return f"db.{db_operation_context.get() or operation}"

    return name


def _get_query_operation(query: str) -> str:
    stripped_query = query.strip()
    if not stripped_query:
        return "UNKNOWN"
    return stripped_query.split(maxsplit=1)[0].upper()


def _db_attrs(client: "PostgresSQLClient", query: str, *_, **__) -> dict:
    return {
        "db.system.name": "postgresql",
        "db.namespace": client.config.database,
        "db.operation.name": _get_query_operation(query),
        "db.query.text": query,
    }


def _procedure_attrs(client: "PostgresSQLClient", proc_name: str, *_, **__) -> dict:
    return {
        "db.system.name": "postgresql",
        "db.namespace": client.config.database,
        "db.operation.name": "CALL",
        "db.stored_procedure.name": proc_name,
    }


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
                # "options": f"-c statement_timeout={self.config.command_timeout * 1000}",
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

    @traced(_db_span_name("execute_query"), attrs=_db_attrs)
    def execute_query(
        self,
        query: str,
        params: tuple | dict | None = None,
        fetch: str = "all",
        commit: bool = False,
    ) -> list[dict[str, Any]] | None:
        """Run a query and return its rows.

        Pass commit=True for writes that use RETURNING, so the change is persisted.
        """

        if fetch not in ("all", "one"):
            raise ValueError("Fetch mode must be either 'all' or 'one'")

        with self.transaction() if commit else self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if fetch == "all":
                    result = [dict(row) for row in cursor.fetchall()]
                elif fetch == "one":
                    row = cursor.fetchone()
                    result = [dict(row)] if row else None
                else:
                    result = None

        return result

    @traced(_db_span_name("execute_command"), attrs=_db_attrs)
    def execute_command(self, query: str, params: tuple | dict | None = None) -> int:

        with self.transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.rowcount

        return result

    @traced(_db_span_name("execute_many"), attrs=_db_attrs)
    def execute_many(self, query: str, params_list: list[tuple | dict]) -> int:

        with self.transaction() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(query, params_list)
                result = cursor.rowcount

        return result

    @traced(_db_span_name("call_procedure"), attrs=_procedure_attrs)
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
                    result = cursor.fetchall()
                except psycopg2.ProgrammingError:
                    result = None

        return result

    def close(self):
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            self.logger.info("Database pool closed")
