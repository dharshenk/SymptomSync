import uuid
import datetime
import logging


class Connection:
    def __init__(self, conn):
        self.connection_id = uuid.uuid4()
        self.is_active = False
        self.last_used = None
        self.conn = conn

    def execute(self, query: str, params: dict | None, fetch_mode: str = "all"):
        try:
            self.cursor = self.conn.cursor()
            self.cursor.execute(query, params) if params else self.cursor.execute(query)
            self.last_used = datetime.datetime.now()
            if query.strip().lower().startswith("select"):
                return self.cursor.fetchall()
        except Exception as e:
            logging.error(f"error executing query {e}")

        finally:
            self.cursor.close()
