import psycopg2
import os
from repository.connection import Connection
import time


class ConnectionPool:
    def __init__(self) -> None:
        self.max_connections = 3
        self.available_connections: list[Connection] = []
        self.pg_conn_params = os.getenv("PG_CONN_PARAMS")

    def get_connection(self):
        if len(self.available_connections) > 0:
            connection = self.available_connections.pop()
            return connection
        elif self.max_connections > 0:
            connection = self._create_connection()
            return connection
        else:
            connection = self.wait_and_pop_connection()

    def release_connection(self, connection: Connection):
        self._add_to_available_connections(connection)

    def _create_connection(self):

        psycopg2_conn = psycopg2.connect(self.pg_conn_params)
        connection = Connection(psycopg2_conn)
        self._add_to_available_connections(connection)
        self.max_connections -= 1
        return connection

    def _add_to_available_connections(self, connection: Connection):
        self.available_connections.append(connection)

    def wait_and_pop_connection(self):
        timeout = 30
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.available_connections:
                return self.available_connections.pop()
            time.sleep(0.1)

        raise TimeoutError(f"No connections available within {timeout} seconds")
