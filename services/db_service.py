import logging
from config.database_config import DatabaseConfig
from repository.connection_pool import ConnectionPool
from repository.transaction import Transaction


class DBService:
    def __init__(self, config: DatabaseConfig) -> None:
        self.connection_pool = None
        self.config = config

    def connect(self):
        if not self.connection_pool:
            self.connection_pool = ConnectionPool(config=self.config)

    def disconnect(self):
        if self.connection_pool:
            self.connection_pool.close_all_connections()
            self.connection_pool = None

    def execute_query(self, query, params: dict | None):
        if self.connection_pool is None:
            raise RuntimeError(
                "Database not connected. Call connect() first or use context manager."
            )
        connection = self.connection_pool.get_connection()
        try:
            result = connection.execute(query, params)
            if result.success:
                connection.commit()
            else:
                connection.rollback()
            return result
        except Exception as e:
            logging.error(
                f"Error from connection: {connection.connection_id} while executing a query: {e}"
            )
            raise
        finally:
            self.connection_pool.release_connection(connection)

    def execute_transaction(self, queries: list, params: list[dict]):
        if self.connection_pool is None:
            raise RuntimeError(
                "Database not connected. Call connect() first or use context manager."
            )

        connection = self.connection_pool.get_connection()
        transaction = Transaction(connection)
        try:
            results = transaction.execute(queries, params)
            if all(r.success for r in results):
                transaction.commit()
            else:
                transaction.rollback()
            return results
        except Exception as e:
            logging.error(
                f"Error from transaction: {transaction.transaction_id} while executing a transaction: {e}"
            )
            raise
        finally:
            self.connection_pool.release_connection(connection)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()
