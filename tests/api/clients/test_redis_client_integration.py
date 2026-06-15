import pytest


@pytest.mark.integration
def test_redis_client_connection(redis_client):
    """Test that the client can connect and ping Redis."""
    assert redis_client.health_check() is True
    assert redis_client.ping() is True


@pytest.mark.integration
def test_set_and_get_string(redis_client):
    key, value = "test_key", "test_value"
    assert redis_client.set_kv(key, value) is True
    assert redis_client.get(key) == value


@pytest.mark.integration
def test_set_and_get_dict(redis_client):
    key, value = "dict_key", {"a": 1, "b": 2}
    assert redis_client.set_kv(key, value) is True
    assert redis_client.get(key, deserialize_json=True) == value


@pytest.mark.integration
def test_delete_and_exists(redis_client):
    key = "delete_key"
    redis_client.set_kv(key, "to_delete")
    assert redis_client.exists(key) is True
    assert redis_client.delete(key) == 1
    assert redis_client.exists(key) is False


@pytest.mark.integration
def test_expire_and_ttl(redis_client):
    key = "expire_key"
    redis_client.set_kv(key, "expiring", ex=2)
    assert redis_client.ttl(key) > 0
    import time

    time.sleep(2)
    assert redis_client.get(key) is None


@pytest.mark.integration
def test_hset_and_hget(redis_client):
    key, field, value = "hash_key", "field1", "val1"
    assert redis_client.hset(key, field, value) == 1
    assert redis_client.hget(key, field) == value
    assert redis_client.hgetall(key) == {field: value}
    assert redis_client.hdel(key, field) == 1


@pytest.mark.integration
def test_lpush_and_lpop(redis_client):
    key = "list_key"
    assert redis_client.lpush(key, "a", "b") == 2
    assert redis_client.llen(key) == 2
    assert redis_client.lpop(key) == "b"
    assert redis_client.rpop(key) == "a"
    assert redis_client.llen(key) == 0


@pytest.mark.integration
def test_sadd_and_smembers(redis_client):
    key = "set_key"
    assert redis_client.sadd(key, "x", "y") == 2
    members = redis_client.smembers(key)
    assert set(members) == {"x", "y"}
    assert redis_client.srem(key, "x") == 1
    assert redis_client.smembers(key) == {"y"}


@pytest.mark.integration
def test_keys_and_flushdb(redis_client):
    redis_client.set_kv("k1", "v1")
    redis_client.set_kv("k2", "v2")
    keys = redis_client.keys("k*")
    assert set(keys) >= {"k1", "k2"}
    assert redis_client.flushdb() is True
    assert redis_client.keys("*") == []
