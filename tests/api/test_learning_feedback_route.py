import asyncio
import hashlib
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import experience_store
from backend.core.auth import auth
from backend import learning_routes


def _client():
    app = FastAPI()
    app.include_router(learning_routes.router)
    return TestClient(app)


def _create_key(name, scope):
    with patch.object(auth, "get_redis", new_callable=AsyncMock, return_value=None):
        return asyncio.run(auth.create_api_key(name, scope=scope))


def _remove_key(key):
    auth._api_key_store.pop(hashlib.sha256(key.encode()).hexdigest(), None)


def test_learning_route_requires_write_scope():
    client = _client()
    response = client.post(
        "/api/learn",
        json={"action": "monitor", "experience_id": "a" * 32},
    )
    assert response.status_code == 401

    read_key = _create_key("learning-feedback-read", "read")
    try:
        response = client.post(
            "/api/learn",
            json={"action": "monitor", "experience_id": "a" * 32},
            headers={"X-API-Key": read_key},
        )
    finally:
        _remove_key(read_key)

    assert response.status_code == 403


def test_learning_route_rejects_success_claim_and_invalid_actions():
    client = _client()
    write_key = _create_key("learning-feedback-validation", "write")
    headers = {"X-API-Key": write_key}

    try:
        caller_success = client.post(
            "/api/learn",
            json={
                "action": "monitor",
                "success": True,
                "experience_id": "a" * 32,
            },
            headers=headers,
        )
        missing_action = client.post(
            "/api/learn",
            json={"experience_id": "a" * 32},
            headers=headers,
        )
        malformed_action = client.post(
            "/api/learn",
            json={"action": 123, "experience_id": "a" * 32},
            headers=headers,
        )
        unsupported_action = client.post(
            "/api/learn",
            json={"action": "arbitrary-action", "experience_id": "a" * 32},
            headers=headers,
        )
        malformed_id = client.post(
            "/api/learn",
            json={"action": "monitor", "experience_id": "../../weights.json"},
            headers=headers,
        )
    finally:
        _remove_key(write_key)

    assert caller_success.status_code == 422
    assert missing_action.status_code == 422
    assert malformed_action.status_code == 422
    assert unsupported_action.status_code == 422
    assert malformed_id.status_code == 422


def test_learning_route_requires_one_matching_trusted_experience(
    tmp_path, monkeypatch
):
    experience_path = tmp_path / "experiences.json"
    monkeypatch.setattr(experience_store, "PATH", str(experience_path))
    experience_id = experience_store.store_experience(
        state=[],
        action="monitor",
        reward=1,
        before={},
        after={},
        verification={"status": "success", "verified": True},
    )
    learned = Mock()
    monkeypatch.setattr(learning_routes, "engine", learned)

    write_key = _create_key("learning-feedback-write", "write")
    client = _client()
    headers = {"X-API-Key": write_key}
    payload = {"action": "monitor", "experience_id": experience_id}

    try:
        updated = client.post("/api/learn", json=payload, headers=headers)
        replayed = client.post("/api/learn", json=payload, headers=headers)
    finally:
        _remove_key(write_key)

    assert updated.status_code == 200
    assert updated.json() == {"status": "updated"}
    learned.learn_from_feedback.assert_called_once_with(
        "monitor",
        {"status": "success", "verified": True},
    )
    assert replayed.status_code == 409
