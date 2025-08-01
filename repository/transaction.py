import logging
import uuid


class Transaction:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.transaction_id = uuid.uuid4()

    def execute(self, query: str, params: dict):
        try:
            self.connection.execute(query, params)
        except Exception as e:
            logging.error(
                f"error executing transaction: {self.transaction_id} when executing: {e}"
            )

    def commit(self):
        try:
            self.connection.commit()
        except Exception as e:
            logging.error(
                f"error executing transaction: {self.transaction_id} when committing: {e}"
            )

    def rollback(self):
        try:
            self.connection.rollback()
        except Exception as e:
            logging.error(
                f"error executing transaction: {self.transaction_id} when rolling back: {e}"
            )
