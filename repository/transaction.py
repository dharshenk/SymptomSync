import logging
import uuid
from models.query_result import QueryResult


class Transaction:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.transaction_id = uuid.uuid4()

    def execute(self, queries: list[str], params_list: list[dict]):
        results = []
        try:
            for query, params in zip(queries, params_list):
                result = self.connection.execute(query, params)
                results.append(result)
                if not result.success:
                    return results  # return partial results upto failure
            return results  # return all results upon success

        except Exception as e:
            logging.error(
                f"error executing transaction: {self.transaction_id} when executing: {e}"
            )
            error_result = QueryResult(rows=[], success=False, error_message=str(e))
            results.append(error_result)
            return results

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
