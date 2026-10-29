import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.auth.auth import create_api_key


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def read_key():
    from backend.core.auth.auth import _api_key_store
    import hashlib
    import os

    key = os.environ["CVIS_API_KEY"]
    entry = _api_key_store[hashlib.sha256(key.encode()).hexdigest()]
    assert entry["scope"] in {"admin", "write", "read"}
    return key


def test_diagnostics_analyze_requires_auth(client):
    response = client.post(
        "/diagnostics/analyze",
        json={"content": "ModuleNotFoundError: No module named 'requests'"},
    )
    assert response.status_code == 401


def test_diagnostics_local_model_status_requires_auth(client):
    response = client.get("/diagnostics/local-model")
    assert response.status_code == 401


def test_diagnostics_analyze_accepts_authenticated_request(client, read_key):
    response = client.post(
        "/diagnostics/analyze",
        headers={"X-API-Key": read_key},
        json={"content": "ModuleNotFoundError: No module named 'requests'"},
    )
    assert response.status_code == 200
    assert "findings" in response.json()


def test_diagnostics_rejects_empty_content(client, read_key):
    response = client.post(
        "/diagnostics/analyze",
        headers={"X-API-Key": read_key},
        json={"content": ""},
    )
    assert response.status_code == 422


def test_diagnostics_rejects_oversized_content(client, read_key):
    from backend.core.diagnostics.log_analyzer import MAX_INPUT_CHARS

    response = client.post(
        "/diagnostics/analyze",
        headers={"X-API-Key": read_key},
        json={"content": "x" * (MAX_INPUT_CHARS + 1)},
    )
    assert response.status_code == 422


def test_local_model_request_without_configuration_returns_400(client, read_key):
    with patch.dict("os.environ", {"CVIS_LOCAL_LLM_MODEL": ""}):
        response = client.post(
            "/diagnostics/analyze",
            headers={"X-API-Key": read_key},
            json={
                "content": "Unknown diagnostic test error",
                "use_local_model": True,
            },
        )

    assert response.status_code == 400
    assert "No local model is configured" in response.json()["detail"]


def test_diagnostics_rejects_insufficient_scope(client):
    import os
    from backend.core.auth.auth import create_api_key

    with patch("backend.core.auth.auth.get_redis", return_value=None):
        key = client.portal.call(create_api_key, "diagnostics-no-access", "none")

    response = client.post(
        "/diagnostics/analyze",
        headers={"X-API-Key": key},
        json={"content": "Test diagnostic authentication"},
    )
    assert response.status_code == 403


def test_local_model_failure_returns_controlled_503(client, read_key):
    with patch.dict("os.environ", {"CVIS_LOCAL_LLM_MODEL": "test-model"}):
        with patch(
            "backend.main.analyze_with_local_model",
            side_effect=RuntimeError("Local model unavailable"),
        ):
            response = client.post(
                "/diagnostics/analyze",
                headers={"X-API-Key": read_key},
                json={
                    "content": "Unknown diagnostic test error",
                    "use_local_model": True,
                },
            )

    assert response.status_code == 503
    assert "Local model analysis failed" in response.json()["detail"]
