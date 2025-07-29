import redis
import json
import logging
import time
from typing import (
    Any,
    Union,
    TypeVar,
    cast,
)
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
import pickle
from types import TracebackType
from pydantic import BaseModel

# Type variables for generic functions
F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")

# Type aliases for better readability
RedisValue = Union[str, bytes, int, float]
SerializableValue = Union[str, bytes, int, float, dict[str, Any], list[Any], None]
DeserializedValue = Union[str, int, float, dict[str, Any], list[Any], None]


@dataclass
class RedisConfig(BaseModel):
    """Redis configuration settings with type annotations"""

    host: str
    port: int
    db: int
    password: str | None = None
    username: str | None = None
    ssl: bool = False
    ssl_cert_reqs: str | None = None
    ssl_ca_certs: str | None = None
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None

    # Connection pool settings
    max_connections: int = 10
    retry_on_timeout: bool = True
    health_check_interval: int = 30

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 0.1
    backoff_factor: float = 2.0

    # Timeout settings
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0


class RedisConnectionError(Exception):
    """Custom Redis connection error"""

    pass


class RedisOperationError(Exception):
    """Custom Redis operation error"""

    pass


def retry_on_connection_error(
    max_retries: int = 3, delay: float = 0.1, backoff: float = 2.0
) -> Callable[[F], F]:
    """Decorator for retrying Redis operations on connection errors"""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(self: "RedisClient", *args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return func(self, *args, **kwargs)
                except (redis.ConnectionError, redis.TimeoutError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        sleep_time = delay * (backoff**attempt)
                        self.logger.warning(
                            f"Redis operation failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {sleep_time:.2f}s..."
                        )
                        time.sleep(sleep_time)
                    else:
                        self.logger.error(
                            f"Redis operation failed after {max_retries + 1} attempts"
                        )

            raise RedisConnectionError(
                f"Failed after {max_retries + 1} attempts: {last_exception}"
            )

        return cast(F, wrapper)

    return decorator


class RedisClient:
    """Production-ready Redis client with connection pooling, error handling, and retry logic"""

    def __init__(self, config: RedisConfig) -> None:
        self.config: RedisConfig = config
        self.logger: logging.Logger = logging.getLogger(__name__)
        self._pool: redis.ConnectionPool | None = None
        self._client: redis.Redis[bytes] | None = None
        self._initialize_connection()

    def _initialize_connection(self) -> None:
        """Initialize Redis connection pool"""
        try:
            self._pool = redis.ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                username=self.config.username,
                ssl=self.config.ssl,
                ssl_cert_reqs=self.config.ssl_cert_reqs,
                ssl_ca_certs=self.config.ssl_ca_certs,
                ssl_certfile=self.config.ssl_certfile,
                ssl_keyfile=self.config.ssl_keyfile,
                max_connections=self.config.max_connections,
                retry_on_timeout=self.config.retry_on_timeout,
                health_check_interval=self.config.health_check_interval,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
            )

            self._client = redis.Redis(connection_pool=self._pool)

            # Test connection
            self._client.ping()
            self.logger.info("Redis connection established successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize Redis connection: {e}")
            raise RedisConnectionError(f"Failed to connect to Redis: {e}")

    @contextmanager
    def get_connection(self) -> Iterator[redis.connection.Connection]:
        """Context manager for getting Redis connection"""
        if self._pool is None:
            raise RedisConnectionError("Connection pool not initialized")

        connection: redis.connection.Connection | None = None
        try:
            connection = self._pool.get_connection("_")
            yield connection
        finally:
            if connection is not None:
                self._pool.release(connection)

    def health_check(self) -> bool:
        """Check if Redis connection is healthy"""
        try:
            if self._client is None:
                return False
            self._client.ping()
            return True
        except Exception as e:
            self.logger.error(f"Redis health check failed: {e}")
            return False

    @retry_on_connection_error()
    def ping(self) -> bool:
        """Ping Redis server"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")
        return self._client.ping()

    def _serialize_value(self, value: SerializableValue) -> str | bytes | int | float:
        """Serialize value for Redis storage"""
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        elif isinstance(value, (str, bytes, int, float)):
            return value
        else:
            return pickle.dumps(value)

    def _deserialize_value(
        self, value: bytes | None, deserialize_json: bool = False
    ) -> DeserializedValue:
        """Deserialize value from Redis"""
        if value is None:
            return None

        decoded_value: str = (
            value.decode("utf-8") if isinstance(value, bytes) else str(value)
        )

        if deserialize_json:
            try:
                return json.loads(decoded_value)
            except (json.JSONDecodeError, TypeError):
                # Try pickle if JSON fails
                try:
                    original_bytes = (
                        value
                        if isinstance(value, bytes)
                        else decoded_value.encode("utf-8")
                    )
                    return pickle.loads(original_bytes)
                except Exception:
                    return decoded_value

        return decoded_value

    # String operations
    @retry_on_connection_error()
    def set_kv(
        self,
        key: str,
        value: SerializableValue,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        """Set a key-value pair with optional expiration"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            serialized_value = self._serialize_value(value)
            result = self._client.set(key, serialized_value, ex=ex, nx=nx)
            return bool(result)
        except Exception as e:
            raise RedisOperationError(f"Failed to set key {key}: {e}")

    @retry_on_connection_error()
    def get(self, key: str, deserialize_json: bool = False) -> DeserializedValue:
        """Get value by key with optional JSON deserialization"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            value = self._client.get(key)
            return self._deserialize_value(value, deserialize_json)
        except Exception as e:
            raise RedisOperationError(f"Failed to get key {key}: {e}")

    @retry_on_connection_error()
    def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            return self._client.delete(*keys)
        except Exception as e:
            raise RedisOperationError(f"Failed to delete keys {keys}: {e}")

    @retry_on_connection_error()
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            return bool(self._client.exists(key))
        except Exception as e:
            raise RedisOperationError(f"Failed to check existence of key {key}: {e}")

    @retry_on_connection_error()
    def expire(self, key: str, seconds: int) -> bool:
        """Set expiration time for a key"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            return bool(self._client.expire(key, seconds))
        except Exception as e:
            raise RedisOperationError(f"Failed to set expiration for key {key}: {e}")

    @retry_on_connection_error()
    def ttl(self, key: str) -> int:
        """Get time to live for a key"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            return self._client.ttl(key)
        except Exception as e:
            raise RedisOperationError(f"Failed to get TTL for key {key}: {e}")

    # Hash operations
    @retry_on_connection_error()
    def hset(self, key: str, field: str, value: SerializableValue) -> int:
        """Set field in hash"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            serialized_value = self._serialize_value(value)
            return self._client.hset(key, field, serialized_value)
        except Exception as e:
            raise RedisOperationError(
                f"Failed to set hash field {field} in key {key}: {e}"
            )

    @retry_on_connection_error()
    def hget(
        self, key: str, field: str, deserialize_json: bool = False
    ) -> DeserializedValue:
        """Get field from hash"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            value = self._client.hget(key, field)
            return self._deserialize_value(value, deserialize_json)
        except Exception as e:
            raise RedisOperationError(
                f"Failed to get hash field {field} from key {key}: {e}"
            )

    @retry_on_connection_error()
    def hgetall(
        self, key: str, deserialize_json: bool = False
    ) -> dict[str, DeserializedValue]:
        """Get all fields from hash"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            result = self._client.hgetall(key)
            decoded_result: dict[str, DeserializedValue] = {}

            for field_bytes, value_bytes in result.items():
                field = (
                    field_bytes.decode("utf-8")
                    if isinstance(field_bytes, bytes)
                    else str(field_bytes)
                )
                decoded_value = self._deserialize_value(value_bytes, deserialize_json)
                decoded_result[field] = decoded_value

            return decoded_result
        except Exception as e:
            raise RedisOperationError(
                f"Failed to get all hash fields from key {key}: {e}"
            )

    @retry_on_connection_error()
    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from hash"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            return self._client.hdel(key, *fields)
        except Exception as e:
            raise RedisOperationError(
                f"Failed to delete hash fields {fields} from key {key}: {e}"
            )

    # List operations
    @retry_on_connection_error()
    def lpush(self, key: str, *values: SerializableValue) -> int:
        """Push values to the left of list"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            processed_values = [self._serialize_value(value) for value in values]
            return self._client.lpush(key, *processed_values)
        except Exception as e:
            raise RedisOperationError(f"Failed to lpush to key {key}: {e}")

    @retry_on_connection_error()
    def rpush(self, key: str, *values: SerializableValue) -> int:
        """Push values to the right of list"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            processed_values = [self._serialize_value(value) for value in values]
            return self._client.rpush(key, *processed_values)
        except Exception as e:
            raise RedisOperationError(f"Failed to rpush to key {key}: {e}")

    @retry_on_connection_error()
    def lpop(self, key: str, deserialize_json: bool = False) -> DeserializedValue:
        """Pop value from left of list"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            value = self._client.lpop(key)
            return self._deserialize_value(value, deserialize_json)
        except Exception as e:
            raise RedisOperationError(f"Failed to lpop from key {key}: {e}")

    @retry_on_connection_error()
    def rpop(self, key: str, deserialize_json: bool = False) -> DeserializedValue:
        """Pop value from right of list"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            value = self._client.rpop(key)
            return self._deserialize_value(value, deserialize_json)
        except Exception as e:
            raise RedisOperationError(f"Failed to rpop from key {key}: {e}")

    @retry_on_connection_error()
    def llen(self, key: str) -> int:
        """Get length of list"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            return self._client.llen(key)
        except Exception as e:
            raise RedisOperationError(f"Failed to get length of list {key}: {e}")

    # Set operations
    @retry_on_connection_error()
    def sadd(self, key: str, *values: SerializableValue) -> int:
        """Add members to set"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            processed_values = [self._serialize_value(value) for value in values]
            return self._client.sadd(key, *processed_values)
        except Exception as e:
            raise RedisOperationError(f"Failed to add to set {key}: {e}")

    @retry_on_connection_error()
    def smembers(
        self, key: str, deserialize_json: bool = False
    ) -> set[DeserializedValue]:
        """Get all members of set"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            members = self._client.smembers(key)
            result: set[DeserializedValue] = set()

            for member_bytes in members:
                decoded_member = self._deserialize_value(member_bytes, deserialize_json)
                # Handle the fact that sets can't contain unhashable types
                if isinstance(decoded_member, (dict, list)):
                    # Convert to string representation for set storage
                    result.add(
                        json.dumps(decoded_member)
                        if decoded_member is not None
                        else None
                    )
                else:
                    result.add(decoded_member)

            return result
        except Exception as e:
            raise RedisOperationError(f"Failed to get members of set {key}: {e}")

    @retry_on_connection_error()
    def srem(self, key: str, *values: SerializableValue) -> int:
        """Remove members from set"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            processed_values = [self._serialize_value(value) for value in values]
            return self._client.srem(key, *processed_values)
        except Exception as e:
            raise RedisOperationError(f"Failed to remove from set {key}: {e}")

    # Utility methods
    @retry_on_connection_error()
    def keys(self, pattern: str = "*") -> list[str]:
        """Get keys matching pattern"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            keys = self._client.keys(pattern)
            return [
                key.decode("utf-8") if isinstance(key, bytes) else str(key)
                for key in keys
            ]
        except Exception as e:
            raise RedisOperationError(f"Failed to get keys with pattern {pattern}: {e}")

    @retry_on_connection_error()
    def flushdb(self) -> bool:
        """Flush current database"""
        if self._client is None:
            raise RedisConnectionError("Redis client not initialized")

        try:
            result = self._client.flushdb()
            return bool(result)
        except Exception as e:
            raise RedisOperationError(f"Failed to flush database: {e}")

    def close(self) -> None:
        """Close Redis connection pool"""
        try:
            if self._pool is not None:
                self._pool.disconnect()
                self.logger.info("Redis connection pool closed")
        except Exception as e:
            self.logger.error(f"Error closing Redis connection pool: {e}")

    def __enter__(self) -> "RedisClient":
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
