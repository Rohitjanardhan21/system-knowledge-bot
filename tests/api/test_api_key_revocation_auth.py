
import asyncio
import hashlib
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_delete_api_key_without_credentials_returns_401(client):
    response = client.delete(
        "/auth/api-keys/" + ("a" * 64),
    )

    assert response.status_code == 401


def test_delete_api_key_with_read_scope_returns_403(client):
    from backend.core.auth.auth import (
        _api_key_store,
        create_api_key,
    )

    with patch(
        "backend.core.auth.auth.get_redis",
        new_callable=AsyncMock,
        return_value=None,
    ):
        read_key = asyncio.run(
            create_api_key("revocation-test-read", scope="read")
        )

    key_hash = hashlib.sha256(read_key.encode()).hexdigest()

    try:
        response = client.delete(
            f"/auth/api-keys/{key_hash}",
            headers={"X-API-Key": read_key},
        )

        assert response.status_code == 403
    finally:
        _api_key_store.pop(key_hash, None)


def test_admin_can_request_api_key_revocation(client):
    import backend.main as main

    target_hash = hashlib.sha256(
        b"synthetic-revocation-test-key"
    ).hexdigest()

    admin_headers = {
        "X-API-Key": os.environ["CVIS_API_KEY"],
    }

    with patch(
        "backend.main.revoke_api_key",
        new_callable=AsyncMock,
        return_value=True,
    ) as revoke:
        response = client.delete(
            f"/auth/api-keys/{target_hash}",
            headers=admin_headers,
        )

    assert response.status_code == 200
    assert response.json() == {"deleted": target_hash}
    revoke.assert_awaited_once_with(target_hash)

def test_create_api_key_rejects_invalid_scope(client):
    admin_headers = {
        "X-API-Key": os.environ["CVIS_API_KEY"],
    }

    with patch(
        "backend.main.create_api_key",
        new_callable=AsyncMock,
    ) as create:
        response = client.post(
            "/auth/api-keys",
            json={
                "name": "invalid-scope-audit",
                "scope": "superadmin",
            },
            headers=admin_headers,
        )

    assert response.status_code == 422
    create.assert_not_awaited()

