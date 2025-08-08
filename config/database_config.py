import os
from dotenv import load_dotenv


class DatabaseConfig:
    def __init__(self):
        load_dotenv()
        self.host = os.getenv("POSTGRES_HOST")
        self.port = os.getenv("POSTGRES_PORT")
        self.database = os.getenv("POSTGRES_DATABASE")
        self.username = os.getenv("POSTGRES_USERNAME")
        self.password = os.getenv("POSTGRES_PASSWORD")
        self.timeout = 30
