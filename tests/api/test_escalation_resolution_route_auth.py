import asyncio
import hashlib
import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_escalation_resolution_without_credentials_returns_401(client):
    response = client.post(
        "/judgment/actions/free-disk-space/resolve-escalation",
    )
    assert response.status_code == 401


def test_escalation_resolution_with_write_scope_returns_403(client):
    from backend.core.auth.auth import _api_key_store, create_api_key

    with patch(
        "backend.core.auth.auth.get_redis",
        new_callable=AsyncMock,
        return_value=None,
    ):
        write_key = asyncio.run(
            create_api_key("escalation-resolution-write-test", scope="write")
        )

    key_hash = hashlib.sha256(write_key.encode()).hexdigest()
    try:
        response = client.post(
            "/judgment/actions/free-disk-space/resolve-escalation",
            headers={"X-API-Key": write_key},
        )
        assert response.status_code == 403
    finally:
        _api_key_store.pop(key_hash, None)


def test_admin_route_resolves_and_audits_escalation(client, tmp_path, monkeypatch):
    from judgment import audit, lifecycle, recovery

    state_path = tmp_path / "latest.json"
    audit_path = tmp_path / "audit.json"
    state_path.write_text(
        json.dumps({
            "actions": [{
                "action": "free-disk-space",
                "status": "failed",
                "retry_count": 2,
                "max_retries": 2,
                "escalation_required": True,
            }],
        }),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(recovery, "STATE_PATH", state_path)
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", tmp_path / "audit.tmp")
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", tmp_path / "audit.lock")

    response = client.post(
        "/judgment/actions/free-disk-space/resolve-escalation",
        headers={"X-API-Key": os.environ["CVIS_API_KEY"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    event = json.loads(audit_path.read_text(encoding="utf-8"))[0]
    assert event["event"] == "escalation-resolved"
    assert event["resolved_by"]
