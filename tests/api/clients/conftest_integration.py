import os
import pytest
from src.api.clients.redis_client import RedisConfig, RedisClient
from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env file
load_dotenv(find_dotenv())


def get_redis_connection_params():
    """
    Fixture to provide real Redis connection parameters from environment variables.
    """
    return {
        "host": os.environ["REDIS_HOST"],
        "port": int(os.environ.get("REDIS_PORT", 6379)),
        "db": int(os.environ.get("REDIS_DB", 0)),
        "password": os.environ.get("REDIS_PASSWORD"),
        "username": os.environ.get("REDIS_USERNAME"),
    }


@pytest.fixture(scope="function")
def redis_client():
    """
    Fixture to provide a real RedisClient instance for integration tests.
    Flushes the DB before each test for isolation.
    """
    redis_connection_params = get_redis_connection_params()
    config = RedisConfig(**redis_connection_params)
    client = RedisClient(config)
    client.flushdb()
    yield client
    client.flushdb()
    client.close()
