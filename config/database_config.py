import os


class DatabaseConfig:
    def __init__(self):
        self.host = os.getenv["POSTGRES_HOST"]
        self.port = os.getenv["POSTGRES_PORT"]
        self.database = os.getenv["POSTGRES_DATABASE_NAME"]
        self.username = os.getenv["POSTGRES_USERNAME"]
        self.password = os.getenv["POSTGRES_PASSWORD"]
        self.timeout = 30
        # self.pool_size =
        # self.ssl_mode =
