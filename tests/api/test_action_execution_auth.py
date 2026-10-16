import asyncio
import hashlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_action_execution_without_credentials_returns_401(client):
    response = client.post(
        "/actions/execute",
        params={"action_id": "clear_temp"},
    )

    assert response.status_code == 401


def test_action_execution_with_write_scope_returns_403(client):
    from backend.core.auth.auth import _api_key_store, create_api_key

    with patch(
        "backend.core.auth.auth.get_redis",
        new_callable=AsyncMock,
        return_value=None,
    ):
        write_key = asyncio.run(
            create_api_key("action-route-write-test", scope="write")
        )

    key_hash = hashlib.sha256(write_key.encode()).hexdigest()
    try:
        response = client.post(
            "/actions/execute",
            params={"action_id": "clear_temp"},
            headers={"X-API-Key": write_key},
        )
        assert response.status_code == 403
    finally:
        _api_key_store.pop(key_hash, None)


def test_admin_action_execution_calls_dispatcher_once(client, monkeypatch):
    import backend.main as main

    assert os.environ.get("CVIS_API_KEY"), (
        "CVIS_API_KEY must be configured for this test"
    )
    dispatcher = MagicMock(return_value={
        "success": True,
        "action_id": "clear_temp",
    })

    monkeypatch.setattr(main, "_execute_action", dispatcher)

    response = client.post(
        "/actions/execute",
        params={"action_id": "clear_temp"},
        headers={"X-API-Key": os.environ["CVIS_API_KEY"]},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    dispatcher.assert_called_once_with("clear_temp")
