import psycopg2
from repository.connection import Connection
import time


class ConnectionPool:
    def __init__(self, config) -> None:
        self.max_connections = 3
        self.available_connections: list[Connection] = []
        self.active_connections: list[Connection] = []
        self.config = config

    def get_connection(self):
        if self.available_connections:
            connection = self.available_connections.pop()
            self.active_connections.append(connection)
            connection.is_active = True
            return connection

        if len(self.active_connections) < self.max_connections:
            connection = self._create_connection()
            self.active_connections.append(connection)
            connection.is_active = True
            return connection

        return self._wait_and_pop_connection()

    def release_connection(self, connection: Connection):
        if connection in self.active_connections:
            self.active_connections.remove(connection)
            connection.is_active = False
            self._add_to_available_connections(connection)

    def _create_connection(self):
        psycopg2_conn = psycopg2.connect(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            user=self.config.username,
            password=self.config.password,
        )
        connection = Connection(psycopg2_conn)
        return connection

    def _add_to_available_connections(self, connection: Connection):
        self.available_connections.append(connection)

    def _wait_and_pop_connection(self):
        timeout = 30
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.available_connections:
                connection = self.available_connections.pop()
                self.active_connections.append(connection)
                connection.is_active = True
                return connection

            time.sleep(0.1)

        raise TimeoutError(f"No connections available within {timeout} seconds")

    def close_all_connections(self):
        """Close all connections when shutting down the pool"""
        all_connections = self.active_connections + self.available_connections
        for connection in all_connections:
            connection.close()
        self.active_connections.clear()
        self.available_connections.clear()
