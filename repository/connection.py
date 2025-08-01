import uuid
import logging
from models.query_result import QueryResult


class Connection:
    def __init__(self, psycopg2_conn):
        self.connection_id = uuid.uuid4()
        self.is_active = None
        self.psycopg2_conn = psycopg2_conn

    def execute(self, query: str, params: dict | None):
        try:
            self.cursor = self.psycopg2_conn.cursor()
            self.cursor.execute(query, params) if params else self.cursor.execute(query)

            if query.strip().lower().startswith("select"):
                rows = self.cursor.fetchall()

            else:
                rows = []

                return QueryResult(rows=rows, success=True, error_message="")

        except Exception as e:
            logging.error(
                f"error from connection:{self.connection_id} when executing query: {e}"
            )
            return QueryResult(rows=rows, success=False, error_message=str(e))

        finally:
            self.cursor.close()

    def commit(self):
        try:
            self.psycopg2_conn.commit()
        except Exception as e:
            logging.error(
                f"error from connection:{self.connection_id} when committing: {e}"
            )

    def rollback(self):
        try:
            self.psycopg2_conn.rollback()
        except Exception as e:
            logging.error(
                f"error from connection: {self.connection_id} when rollingback: {e}"
            )

    def close(self):
        if self.psycopg2_conn:
            try:
                self.psycopg2_conn.close()
            except Exception as e:
                logging.error(
                    f"error from connection {self.connection_id} when closing: {e}"
                )
