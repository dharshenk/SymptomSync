import psycopg2
import os
from repository.connection import Connection


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
            connection = self.create_connection()
            return connection
        else:
            pass

    def release_connection(self, connection: Connection):
        self.add_to_available_connections(connection)

    def create_connection(self):

        psycopg2_conn = psycopg2.connect(self.pg_conn_params)
        connection = Connection(psycopg2_conn)
        self.add_to_available_connections(connection)
        self.max_connections -= 1
        return connection

    def add_to_available_connections(self, connection: Connection):
        self.available_connections.append(connection)
