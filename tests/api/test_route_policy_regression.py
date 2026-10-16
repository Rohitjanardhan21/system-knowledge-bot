import asyncio
import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.core.auth.auth import _api_key_store, create_api_key
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def api_key_factory():
    created_hashes = []

    def create_scoped_key(scope):
        with patch(
            "backend.core.auth.auth.get_redis",
            new_callable=AsyncMock,
            return_value=None,
        ):
            key = asyncio.run(
                create_api_key(
                    f"route-policy-{scope}-test",
                    scope=scope,
                )
            )

        created_hashes.append(hashlib.sha256(key.encode()).hexdigest())
        return key

    yield create_scoped_key

    for key_hash in created_hashes:
        _api_key_store.pop(key_hash, None)


READ_ROUTES = [
    ("GET", "/health/full"),
    ("GET", "/devices"),
    ("GET", "/devices/test-device"),
    ("GET", "/report/weekly"),
    ("GET", "/stress/scenarios"),
    ("GET", "/stress/status"),
]

ADMIN_ROUTES = [
    ("POST", "/stress/start/test-scenario"),
    ("POST", "/stress/stop/test-scenario"),
    ("POST", "/stress/stop"),
]

ALL_ROUTES = READ_ROUTES + ADMIN_ROUTES


@pytest.mark.parametrize(
    ("method", "path"),
    ALL_ROUTES,
    ids=[f"{method}-{path}" for method, path in ALL_ROUTES],
)
def test_route_rejects_missing_credentials(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    READ_ROUTES,
    ids=[f"{method}-{path}" for method, path in READ_ROUTES],
)
def test_write_scope_can_access_read_routes(
    client, api_key_factory, monkeypatch, method, path
):
    import backend.main as main

    monkeypatch.setattr(main, "_devices", {
        "test-device": {
            "device_name": "test-device",
            "last_seen": 0,
        }
    })

    key = api_key_factory("write")
    response = client.request(
        method,
        path,
        headers={"X-API-Key": key},
    )

    assert response.status_code not in (401, 403), (
        f"{method} {path} unexpectedly denied write scope: "
        f"{response.status_code}"
    )


@pytest.mark.parametrize(
    ("method", "path"),
    ADMIN_ROUTES,
    ids=[f"{method}-{path}" for method, path in ADMIN_ROUTES],
)
@pytest.mark.parametrize("scope", ["read", "write"])
def test_stress_mutations_reject_non_admin_scope(
    client, api_key_factory, method, path, scope
):
    key = api_key_factory(scope)

    response = client.request(
        method,
        path,
        headers={"X-API-Key": key},
    )

    assert response.status_code == 403


def test_read_key_can_reach_read_routes(
    client, api_key_factory, monkeypatch
):
    from backend.core.demo import stress_engine
    import backend.main as main

    monkeypatch.setattr(main, "_devices", {
        "test-device": {
            "device_name": "test-device",
            "last_seen": 0,
        }
    })

    monkeypatch.setattr(
        stress_engine, "get_scenarios", lambda: []
    )
    monkeypatch.setattr(
        stress_engine, "get_status", lambda: {"running": False}
    )

    key = api_key_factory("read")

    for method, path in READ_ROUTES:
        response = client.request(
            method,
            path,
            headers={"X-API-Key": key},
        )
        assert response.status_code not in (401, 403), (
            f"{method} {path} unexpectedly denied valid read scope: "
            f"{response.status_code}"
        )


def test_admin_key_can_reach_stress_mutations(
    client, api_key_factory, monkeypatch
):
    from backend.core.demo import stress_engine

    monkeypatch.setattr(
        stress_engine,
        "start_scenario",
        lambda scenario_id: {"success": True},
    )
    monkeypatch.setattr(
        stress_engine,
        "stop_scenario",
        lambda scenario_id: {"success": True},
    )
    monkeypatch.setattr(
        stress_engine,
        "stop_all",
        lambda: {"success": True},
    )

    key = api_key_factory("admin")

    for method, path in ADMIN_ROUTES:
        response = client.request(
            method,
            path,
            headers={"X-API-Key": key},
        )
        assert response.status_code not in (401, 403), (
            f"{method} {path} unexpectedly denied admin scope: "
            f"{response.status_code}"
        )
