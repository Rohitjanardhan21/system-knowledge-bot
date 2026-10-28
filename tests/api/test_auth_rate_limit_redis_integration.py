import hashlib
import uuid

import pytest
from fastapi import HTTPException
from redis.asyncio import Redis
from starlette.requests import Request

from backend import main


@pytest.mark.asyncio
async def test_auth_rate_limit_lua_script_with_real_redis():
    redis = Redis.from_url(
        "redis://localhost:6379/15",
        decode_responses=True,
    )
    key = f"test:auth-rate-limit:{uuid.uuid4().hex}"
    script = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return count
    """
    try:
        assert await redis.ping()
        first = await redis.eval(script, 1, key, 60)
        assert first == 1
        ttl_first = await redis.ttl(key)
        assert 0 < ttl_first <= 60
        second = await redis.eval(script, 1, key, 60)
        assert second == 2
        ttl_second = await redis.ttl(key)
        assert 0 < ttl_second <= ttl_first
        assert await redis.get(key) == "2"
    finally:
        await redis.delete(key)
        await redis.aclose()


@pytest.mark.asyncio
async def test_auth_rate_limit_enforces_limit_with_real_redis(monkeypatch):
    redis = Redis.from_url(
        "redis://localhost:6379/15",
        decode_responses=True,
    )
    operation = f"integration-{uuid.uuid4().hex}"
    client_host = "127.0.0.1"
    identity = f"user-{uuid.uuid4().hex}@example.com"
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "headers": [],
            "client": (client_host, 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )

    def make_key(scope, value):
        bucket = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"cvis:auth:{operation}:{scope}:{bucket}"

    keys = [
        make_key("ip", client_host),
        make_key("identity", identity.casefold()),
    ]

    async def use_real_redis():
        return redis

    monkeypatch.setattr(main, "get_redis", use_real_redis)
    try:
        assert await redis.ping()
        for _ in range(2):
            await main._enforce_auth_rate_limit(
                request,
                operation,
                limit=2,
                window_seconds=60,
                identity=identity,
            )

        with pytest.raises(HTTPException) as error:
            await main._enforce_auth_rate_limit(
                request,
                operation,
                limit=2,
                window_seconds=60,
                identity=identity,
            )

        assert error.value.status_code == 429
        assert await redis.get(keys[0]) == "3"
        assert await redis.get(keys[1]) == "2"
    finally:
        await redis.delete(*keys)
        await redis.aclose()


@pytest.mark.asyncio
async def test_auth_rate_limit_isolates_users_with_real_redis(monkeypatch):
    redis = Redis.from_url(
        "redis://localhost:6379/15",
        decode_responses=True,
    )
    operation = f"isolation-{uuid.uuid4().hex}"
    user_a = f"a-{uuid.uuid4().hex}@example.com"
    user_b = f"b-{uuid.uuid4().hex}@example.com"

    def make_request(client_host):
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/test",
                "headers": [],
                "client": (client_host, 12345),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

    def make_key(scope, value):
        bucket = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"cvis:auth:{operation}:{scope}:{bucket}"

    ip_a1 = "192.0.2.11"
    ip_a2 = "192.0.2.12"
    ip_b = "192.0.2.13"
    keys = [
        make_key("ip", ip_a1),
        make_key("ip", ip_a2),
        make_key("ip", ip_b),
        make_key("identity", user_a.casefold()),
        make_key("identity", user_b.casefold()),
    ]

    async def use_real_redis():
        return redis

    monkeypatch.setattr(main, "get_redis", use_real_redis)
    try:
        assert await redis.ping()
        await main._enforce_auth_rate_limit(
            make_request(ip_a1),
            operation,
            limit=1,
            window_seconds=60,
            identity=user_a,
        )

        with pytest.raises(HTTPException) as error:
            await main._enforce_auth_rate_limit(
                make_request(ip_a2),
                operation,
                limit=1,
                window_seconds=60,
                identity=user_a,
            )
        assert error.value.status_code == 429

        await main._enforce_auth_rate_limit(
            make_request(ip_b),
            operation,
            limit=1,
            window_seconds=60,
            identity=user_b,
        )

        assert await redis.get(keys[0]) == "1"
        assert await redis.get(keys[1]) == "1"
        assert await redis.get(keys[2]) == "1"
        assert await redis.get(keys[3]) == "2"
        assert await redis.get(keys[4]) == "1"
    finally:
        await redis.delete(*keys)
        await redis.aclose()


@pytest.mark.asyncio
async def test_auth_rate_limit_counter_expires_with_real_redis():
    redis = Redis.from_url(
        "redis://localhost:6379/15",
        decode_responses=True,
    )
    key = f"test:auth-rate-limit-expiry:{uuid.uuid4().hex}"
    script = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return count
    """
    try:
        assert await redis.ping()
        assert await redis.eval(script, 1, key, 2) == 1
        assert await redis.get(key) == "1"
        assert await redis.eval(script, 1, key, 2) == 2

        import asyncio

        await asyncio.sleep(2.5)
        assert await redis.get(key) is None
        assert await redis.eval(script, 1, key, 2) == 1
    finally:
        await redis.delete(key)
        await redis.aclose()
