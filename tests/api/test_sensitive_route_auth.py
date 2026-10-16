import asyncio
import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.core.auth.auth import _api_key_store, create_api_key
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


SENSITIVE_ROUTES = [
    ("GET", "/stream", {}),
    ("GET", "/metrics", {}),
    ("GET", "/os/processes", {}),
    ("GET", "/ml/status", {}),
    ("GET", "/db/snapshots", {}),
    ("GET", "/db/events", {}),
    ("GET", "/debug/cpu", {}),
    ("GET", "/alerts/history", {}),
    ("GET", "/alerts/stats", {}),
    ("GET", "/alerts/rules", {}),
    ("POST", "/alerts/webhooks", {
        "json": {"url": "https://example.invalid/hook", "name": "test"},
    }),
    ("DELETE", "/alerts/webhooks/test-id", {}),
    ("POST", "/alerts/webhooks/test-id/test", {}),
    ("PUT", "/alerts/email", {
        "json": {
            "host": "mail.example.invalid",
            "from_addr": "from@example.invalid",
            "to_addrs": ["to@example.invalid"],
        },
    }),
    ("POST", "/alerts/rules", {
        "json": {
            "name": "test",
            "metric": "cpu",
            "operator": ">",
            "threshold": 90,
        },
    }),
    ("DELETE", "/alerts/rules/test-id", {}),
    ("PATCH", "/alerts/rules/test-id", {"params": {"enabled": True}}),
    ("GET", "/cognitive/health-score", {}),
    ("GET", "/cognitive/pipeline", {}),
    ("GET", "/cognitive/forecast", {}),
    ("GET", "/cognitive/predictions", {}),
    ("GET", "/cognitive/debug/matcher", {}),
    ("POST", "/cognitive/predictions/test-id/acknowledge", {}),
    ("POST", "/cognitive/predictions/test-id/resolve", {
        "params": {"was_correct": True},
    }),
    ("GET", "/cognitive/dna", {}),
    ("GET", "/cognitive/premortem", {}),
    ("GET", "/cognitive/remediation/status", {}),
    ("GET", "/cognitive/remediation/log", {}),
    ("GET", "/cognitive/blackbox", {}),
    ("POST", "/cognitive/incident", {
        "params": {"incident_type": "TEST"},
    }),
    ("GET", "/cognitive/incidents", {}),
    ("GET", "/cognitive/incidents/test-id", {}),
    ("GET", "/cognitive/postmortem/test-id", {}),
    ("GET", "/cognitive/notifications", {}),
    ("POST", "/cognitive/notifications/config", {}),
    ("GET", "/cognitive/status", {}),
    ("GET", "/cognitive/degradation", {}),
    ("GET", "/settings", {}),
    ("POST", "/settings", {"json": {}}),
    ("POST", "/settings/reset", {}),
    ("POST", "/settings/test-email", {}),
    ("POST", "/settings/send-report", {}),
]


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    SENSITIVE_ROUTES,
    ids=[f"{method}-{path}" for method, path, _ in SENSITIVE_ROUTES],
)
def test_sensitive_routes_reject_missing_credentials(
    client,
    method,
    path,
    kwargs,
):
    response = client.request(method, path, **kwargs)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("scope", "method", "path", "kwargs"),
    [
        ("read", "POST", "/settings/reset", {}),
        ("write", "POST", "/settings/reset", {}),
        ("read", "POST", "/alerts/webhooks", {
            "json": {"url": "https://example.invalid/hook", "name": "test"},
        }),
        ("read", "POST", "/cognitive/incident", {
            "params": {"incident_type": "TEST"},
        }),
    ],
)
def test_insufficient_scope_is_rejected(
    client,
    scope,
    method,
    path,
    kwargs,
):
    with patch(
        "backend.core.auth.auth.get_redis",
        new_callable=AsyncMock,
        return_value=None,
    ):
        api_key = asyncio.run(create_api_key(
            f"sensitive-route-{scope}-test",
            scope=scope,
        ))

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    try:
        response = client.request(
            method,
            path,
            headers={"X-API-Key": api_key},
            **kwargs,
        )

        assert response.status_code == 403
    finally:
        _api_key_store.pop(key_hash, None)
