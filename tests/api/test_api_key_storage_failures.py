import asyncio
import hashlib
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.core.auth import auth


def run(coro):
    return asyncio.run(coro)


def test_create_key_persists_before_caching():
    fake_redis = AsyncMock()
    fake_redis.hset.return_value = 1

    with (
        patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=fake_redis),
        patch.dict("os.environ", {"ENV": "dev"}),
    ):
        key = run(auth.create_api_key("test-persist", scope="read"))

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    try:
        fake_redis.hset.assert_awaited_once()
        assert key_hash in auth._api_key_store
        assert key_hash in auth._redis_backed_api_keys
    finally:
        auth._api_key_store.pop(key_hash, None)
        auth._redis_backed_api_keys.discard(key_hash)


def test_create_key_fails_closed_when_redis_write_fails():
    fake_redis = AsyncMock()
    fake_redis.hset.side_effect = RuntimeError("simulated Redis failure")

    with patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=fake_redis):
        with pytest.raises(HTTPException) as exc:
            run(auth.create_api_key("test-write-failure", scope="read"))

    assert exc.value.status_code == 503


def test_create_key_fails_closed_when_env_is_unset_and_redis_is_unavailable():
    fake_env = {
        key: value
        for key, value in os.environ.items()
        if key != "ENV"
    }

    with (
        patch.dict("os.environ", fake_env, clear=True),
        patch.object(
            auth,
            "get_redis",
            new_callable=AsyncMock,
            return_value=None,
        ),
        pytest.raises(HTTPException) as exc,
    ):
        run(auth.create_api_key("env-unset-regression", scope="read"))

    assert exc.value.status_code == 503
    assert exc.value.detail == "API-key storage is unavailable"


def test_revoke_key_keeps_cache_if_redis_delete_fails():
    key_hash = hashlib.sha256(b"test-revoke-failure").hexdigest()
    auth._api_key_store[key_hash] = {
        "name": "test-revoke-failure",
        "scope": "read",
        "created_at": "0",
    }
    auth._redis_backed_api_keys.add(key_hash)

    fake_redis = AsyncMock()
    fake_redis.delete.side_effect = RuntimeError("simulated Redis failure")

    try:
        with patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=fake_redis):
            with pytest.raises(HTTPException) as exc:
                run(auth.revoke_api_key(key_hash))

        assert exc.value.status_code == 503
        assert key_hash in auth._api_key_store
    finally:
        auth._api_key_store.pop(key_hash, None)
        auth._redis_backed_api_keys.discard(key_hash)


def test_revoke_local_only_key_when_redis_is_unavailable():
    key_hash = hashlib.sha256(b"test-local-only-revoke").hexdigest()
    auth._api_key_store[key_hash] = {
        "name": "test-local-only",
        "scope": "read",
        "created_at": "0",
    }
    auth._redis_backed_api_keys.discard(key_hash)

    try:
        with patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=None):
            assert run(auth.revoke_api_key(key_hash)) is True

        assert key_hash not in auth._api_key_store
    finally:
        auth._api_key_store.pop(key_hash, None)
        auth._redis_backed_api_keys.discard(key_hash)


def test_revoke_unknown_key_does_not_report_success():
    key_hash = hashlib.sha256(b"test-unknown-key").hexdigest()
    fake_redis = AsyncMock()
    fake_redis.delete.return_value = 0

    with patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=fake_redis):
        with pytest.raises(HTTPException) as exc:
            run(auth.revoke_api_key(key_hash))

    assert exc.value.status_code == 404

def test_verify_rejects_cached_key_after_redis_revocation():
    key = "synthetic-test-key-for-revocation"
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    auth._api_key_store[key_hash] = {
        "name": "revoked-test-key",
        "scope": "read",
        "created_at": "0",
    }
    auth._redis_backed_api_keys.add(key_hash)

    fake_redis = AsyncMock()
    fake_redis.hgetall.return_value = {}

    try:
        with patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=fake_redis):
            with pytest.raises(HTTPException) as exc:
                run(auth._verify_api_key(key))

        assert exc.value.status_code == 401
        assert key_hash not in auth._api_key_store
        fake_redis.hgetall.assert_awaited_once_with(f"api_key:{key_hash}")
    finally:
        auth._api_key_store.pop(key_hash, None)
        auth._redis_backed_api_keys.discard(key_hash)


def test_verify_returns_503_when_redis_backed_key_cannot_be_checked():
    key = "synthetic-test-key-redis-unavailable"
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    auth._api_key_store[key_hash] = {
        "name": "redis-unavailable-test-key",
        "scope": "read",
        "created_at": "0",
    }
    auth._redis_backed_api_keys.add(key_hash)

    try:
        with patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc:
                run(auth._verify_api_key(key))

        assert exc.value.status_code == 503
    finally:
        auth._api_key_store.pop(key_hash, None)
        auth._redis_backed_api_keys.discard(key_hash)

def test_verify_unknown_key_returns_503_when_redis_is_unavailable():
    key = "synthetic-unknown-key-during-redis-outage"

    with patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=None):
        with pytest.raises(HTTPException) as exc:
            run(auth._verify_api_key(key))

    assert exc.value.status_code == 503

def test_verify_unknown_key_returns_503_when_redis_is_unavailable():
    key = "synthetic-unknown-key-during-redis-outage"

    with patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=None):
        with pytest.raises(HTTPException) as exc:
            run(auth._verify_api_key(key))

    assert exc.value.status_code == 503

def test_bootstrap_key_cannot_be_revoked_through_api_key_manager():
    bootstrap_hash = hashlib.sha256(
        auth.BOOTSTRAP_API_KEY.encode()
    ).hexdigest()

    with pytest.raises(HTTPException) as exc:
        run(auth.revoke_api_key(bootstrap_hash))

    assert exc.value.status_code == 409
