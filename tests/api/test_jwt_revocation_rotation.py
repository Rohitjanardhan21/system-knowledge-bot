import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.core.auth import auth


class RedisStub:
    def __init__(self, *, revoked=None, fail_get=False, fail_set=False):
        self.revoked = revoked
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.used = set()

    async def get(self, _key):
        if self.fail_get:
            raise ConnectionError("Redis unavailable")
        return self.revoked

    async def set(self, key, value, *, ex, nx):
        if self.fail_set:
            raise ConnectionError("Redis unavailable")
        assert value == "1"
        assert ex > 0
        assert nx is True
        if key in self.used:
            return None
        self.used.add(key)
        return True


pytestmark = pytest.mark.skipif(
    not auth.JWT_OK,
    reason="PyJWT is required for JWT authentication tests",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_revoked_access_token_is_rejected(monkeypatch):
    token = auth._issue_access_token("test-user", "read")
    monkeypatch.setattr(
        auth, "get_redis", _async_return(RedisStub(revoked="1"))
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth._verify_jwt(token))

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token revoked"


@pytest.mark.parametrize(
    "redis",
    [None, RedisStub(fail_get=True)],
    ids=["redis-missing", "redis-error"],
)
def test_access_token_verification_fails_closed(monkeypatch, redis):
    token = auth._issue_access_token("test-user", "read")
    monkeypatch.setattr(auth, "get_redis", _async_return(redis))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth._verify_jwt(token))

    assert exc.value.status_code == 503


@pytest.mark.parametrize(
    ("configured_secret", "missing_secret"),
    [
        (None, "JWT_SECRET"),
        ("JWT_SECRET", "CVIS_API_KEY"),
    ],
)
def test_production_import_requires_explicit_secrets(
    configured_secret,
    missing_secret,
):
    env = os.environ.copy()
    for secret in (
        "JWT_SECRET",
        "JWT_SECRET_FILE",
        "CVIS_API_KEY",
        "CVIS_API_KEY_FILE",
    ):
        env.pop(secret, None)
    env["ENV"] = "production"
    if configured_secret:
        env[configured_secret] = "test-configured-secret"

    result = subprocess.run(
        [sys.executable, "-c", "import backend.core.auth.auth"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert f"{missing_secret} must be configured" in result.stderr


def test_refresh_token_can_be_consumed_only_once(monkeypatch):
    redis = RedisStub()
    monkeypatch.setattr(auth, "get_redis", _async_return(redis))
    pair = auth.issue_token_pair("test-user", "read")

    rotated = asyncio.run(auth.refresh_access_token(pair.refresh_token))
    assert rotated.access_token
    assert rotated.refresh_token

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.refresh_access_token(pair.refresh_token))

    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "redis",
    [None, RedisStub(fail_set=True)],
    ids=["redis-missing", "redis-error"],
)
def test_refresh_rotation_fails_closed(monkeypatch, redis):
    monkeypatch.setattr(auth, "get_redis", _async_return(redis))
    pair = auth.issue_token_pair("test-user", "read")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.refresh_access_token(pair.refresh_token))

    assert exc.value.status_code == 503


def _async_return(value):
    async def get_value():
        return value

    return get_value
