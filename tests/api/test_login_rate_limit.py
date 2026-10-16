from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.main as main


class RedisCounterStub:
    def __init__(self, fail=False):
        self.count = 0
        self.fail = fail
        self.keys = []

    async def eval(self, script, numkeys, key, window_s):
        if self.fail:
            raise ConnectionError("Redis unavailable")
        assert numkeys == 1
        assert window_s == 60
        self.keys.append(key)
        self.count += 1
        return self.count


def async_return(value):
    async def _get():
        return value
    return _get


@pytest.fixture
def login_client(monkeypatch):
    monkeypatch.setattr(main, "_USERS", {"admin": "test-admin-pass"})
    monkeypatch.setattr(
        main,
        "issue_token_pair",
        lambda username, scope: SimpleNamespace(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_in=900,
        ),
    )
    with TestClient(main.app, raise_server_exceptions=True) as client:
        yield client


def test_five_failed_logins_return_401(login_client, monkeypatch):
    redis = RedisCounterStub()
    monkeypatch.setattr(main, "get_redis", async_return(redis))

    for _ in range(5):
        response = login_client.post(
            "/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == 401

    assert redis.count == 5
    assert len(set(redis.keys)) == 1


def test_sixth_failed_login_returns_429(login_client, monkeypatch):
    redis = RedisCounterStub()
    monkeypatch.setattr(main, "get_redis", async_return(redis))

    for _ in range(5):
        login_client.post(
            "/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    response = login_client.post(
        "/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert response.status_code == 429


def test_valid_login_still_works_after_five_failures(
    login_client, monkeypatch
):
    redis = RedisCounterStub()
    monkeypatch.setattr(main, "get_redis", async_return(redis))

    for _ in range(5):
        login_client.post(
            "/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    response = login_client.post(
        "/auth/login",
        json={"username": "admin", "password": "test-admin-pass"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "test-access-token"


@pytest.mark.parametrize("redis", [None, RedisCounterStub(fail=True)])
def test_login_fails_closed_when_redis_is_unavailable(
    login_client, monkeypatch, redis
):
    monkeypatch.setattr(main, "get_redis", async_return(redis))

    response = login_client.post(
        "/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == 503


@pytest.mark.parametrize("invalid_count", [True, False, "5", None, 5.0])
def test_login_fails_closed_on_invalid_redis_counter(
    login_client, monkeypatch, invalid_count
):
    class InvalidCounterRedis:
        async def eval(self, script, numkeys, key, window_s):
            return invalid_count

    monkeypatch.setattr(
        main, "get_redis", async_return(InvalidCounterRedis())
    )

    response = login_client.post(
        "/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == 503
