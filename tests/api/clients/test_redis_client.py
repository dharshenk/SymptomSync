import pytest
from unittest.mock import patch, MagicMock
from src.api.clients.redis_client import (
    RedisClient,
    RedisConfig,
    RedisConnectionError,
)


@pytest.fixture
def redis_config():
    return RedisConfig(
        host="localhost",
        port=6379,
        db=0,
        password=None,
        username=None,
    )


def test_redis_config_instantiation(redis_config):
    # Test that RedisConfig fields are set correctly
    assert redis_config.host == "localhost"
    assert redis_config.port == 6379
    assert redis_config.db == 0
    assert redis_config.password is None
    assert redis_config.username is None


def test_redis_client_initialization_success(redis_config):
    # Test successful initialization and health check
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client._client is not None
        assert client.health_check() is True


def test_redis_client_initialization_failure(redis_config):
    # Test initialization failure raises RedisConnectionError
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_redis.side_effect = Exception("Connection failed")
        mock_pool.return_value = MagicMock()
        with pytest.raises(RedisConnectionError):
            RedisClient(redis_config)


def test_redis_client_context_manager(redis_config):
    # Test context manager enters and exits, calling close
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        with patch.object(RedisClient, "close", autospec=True) as mock_close:
            with RedisClient(redis_config) as client:
                assert isinstance(client, RedisClient)
            mock_close.assert_called_once_with(client)


def test_get_connection_yields_and_releases(redis_config):
    # Test get_connection yields a connection and releases it
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis.return_value = mock_instance
        mock_conn = MagicMock()
        mock_pool_instance = MagicMock()
        mock_pool_instance.get_connection.return_value = mock_conn
        mock_pool_instance.release.return_value = None
        mock_pool.return_value = mock_pool_instance

        client = RedisClient(redis_config)
        with client.get_connection() as conn:
            assert conn == mock_conn
        mock_pool_instance.release.assert_called_once_with(mock_conn)


# --- Serialization/Deserialization ---
def test_serialize_and_deserialize_value(redis_config):
    # Patch Redis and ConnectionPool to avoid real connection
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_redis.return_value = MagicMock()
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        # Test serialization
        assert client._serialize_value("foo") == "foo"
        assert client._serialize_value(123) == 123
        assert client._serialize_value(12.5) == 12.5
        assert isinstance(client._serialize_value({"a": 1}), str)
        assert isinstance(client._serialize_value([1, 2, 3]), str)
        # Test deserialization
        assert client._deserialize_value(b"bar") == "bar"
        assert client._deserialize_value(None) is None
        # JSON deserialization
        import json

        d = {"a": 1}
        s = json.dumps(d).encode()
        assert client._deserialize_value(s, deserialize_json=True) == d


# --- String Operations ---
def test_set_and_get(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.set.return_value = True
        mock_instance.get.return_value = b"value"
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.set_kv("key", "value") is True
        assert client.get("key") == "value"


def test_delete_and_exists(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.delete.return_value = 1
        mock_instance.exists.return_value = True
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.delete("key") == 1
        assert client.exists("key") is True


def test_expire_and_ttl(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.expire.return_value = True
        mock_instance.ttl.return_value = 100
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.expire("key", 10) is True
        assert client.ttl("key") == 100


# --- Hash Operations ---
def test_hset_and_hget(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.hset.return_value = 1
        mock_instance.hget.return_value = b"val"
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.hset("hkey", "field", "val") == 1
        assert client.hget("hkey", "field") == "val"


def test_hgetall_and_hdel(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.hgetall.return_value = {b"f": b"v"}
        mock_instance.hdel.return_value = 1
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.hgetall("hkey") == {"f": "v"}
        assert client.hdel("hkey", "f") == 1


# --- List Operations ---
def test_lpush_and_rpush(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.lpush.return_value = 2
        mock_instance.rpush.return_value = 2
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.lpush("lkey", "a", "b") == 2
        assert client.rpush("lkey", "a", "b") == 2


def test_lpop_and_rpop(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.lpop.return_value = b"left"
        mock_instance.rpop.return_value = b"right"
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.lpop("lkey") == "left"
        assert client.rpop("lkey") == "right"


def test_llen(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.llen.return_value = 3
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.llen("lkey") == 3


# --- Set Operations ---
def test_sadd_and_smembers(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.sadd.return_value = 2
        mock_instance.smembers.return_value = {b"a", b"b"}
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.sadd("skey", "a", "b") == 2
        assert client.smembers("skey") == {"a", "b"}


def test_srem(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.srem.return_value = 1
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.srem("skey", "a") == 1


# --- Utility Methods ---
def test_keys_and_flushdb(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.keys.return_value = [b"a", b"b"]
        mock_instance.flushdb.return_value = True
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.keys("*") == ["a", "b"]
        assert client.flushdb() is True


# --- Edge Cases ---
def test_set_and_get_none_value(redis_config):
    with (
        patch("api.clients.redis_client.redis.Redis") as mock_redis,
        patch("api.clients.redis_client.redis.ConnectionPool") as mock_pool,
    ):
        mock_instance = MagicMock()
        mock_instance.set.return_value = True
        mock_instance.get.return_value = None
        mock_redis.return_value = mock_instance
        mock_pool.return_value = MagicMock()
        client = RedisClient(redis_config)
        assert client.set_kv("key", None) is True
        assert client.get("key") is None
