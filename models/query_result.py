class QueryResult:
    def __init__(self, rows: list[dict], success: bool, error_message: str) -> None:
        self.rows: list[dict]
        self.success = success
        self.error_message = error_message
