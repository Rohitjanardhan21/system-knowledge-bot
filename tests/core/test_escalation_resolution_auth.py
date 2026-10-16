import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

import pytest

from judgment import audit, lifecycle, recovery


ADMIN_PRINCIPAL = {
    "scope": "admin",
    "_source": "api_key",
    "name": "escalation-reviewer",
}


@pytest.fixture
def isolated_escalation_state(tmp_path, monkeypatch):
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
                "execution_result": "retry-limit-reached",
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
    return state_path, audit_path


def test_resolution_requires_authenticated_admin_principal(
    isolated_escalation_state,
):
    with pytest.raises(PermissionError):
        lifecycle.resolve_escalation(
            "free-disk-space",
            principal={"scope": "write", "_source": "api_key", "name": "writer"},
        )

    with pytest.raises(PermissionError):
        lifecycle.resolve_escalation(
            "free-disk-space",
            principal={"scope": "admin", "name": "spoofed"},
        )

    state_path, _ = isolated_escalation_state
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["actions"][0]["status"] == "failed"
    assert state["actions"][0]["escalation_required"] is True


def test_admin_resolution_is_durable_and_audits_actor(
    isolated_escalation_state,
):
    state_path, audit_path = isolated_escalation_state

    result = lifecycle.resolve_escalation(
        "free-disk-space",
        principal=ADMIN_PRINCIPAL,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = state["actions"][0]
    events = json.loads(audit_path.read_text(encoding="utf-8"))

    assert result["status"] == "approved"
    assert action["status"] == "approved"
    assert action["retry_count"] == 0
    assert action["escalation_required"] is False
    assert action["escalation_resolved_by"] == "escalation-reviewer"
    assert len(events) == 1
    assert events[0]["event"] == "escalation-resolved"
    assert events[0]["resolved_by"] == "escalation-reviewer"
    assert events[0]["resolution_id"] == action["escalation_resolution_id"]


def test_concurrent_resolutions_transition_once(isolated_escalation_state):
    _, audit_path = isolated_escalation_state

    def resolve():
        return lifecycle.resolve_escalation(
            "free-disk-space",
            principal=ADMIN_PRINCIPAL,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: resolve(), range(8)))

    assert sum(result["status"] == "approved" for result in results) == 1
    assert sum(result["status"] == "blocked" for result in results) == 7
    events = json.loads(audit_path.read_text(encoding="utf-8"))
    assert sum(event["event"] == "escalation-resolved" for event in events) == 1


def test_recovery_reconciles_audit_after_resolution_crash(
    isolated_escalation_state,
    monkeypatch,
):
    state_path, audit_path = isolated_escalation_state

    def crash_before_audit(_events):
        raise OSError("simulated process failure after state commit")

    monkeypatch.setattr(lifecycle, "record_execution", crash_before_audit)
    with pytest.raises(OSError, match="simulated process failure"):
        lifecycle.resolve_escalation(
            "free-disk-space",
            principal=ADMIN_PRINCIPAL,
        )

    committed = json.loads(state_path.read_text(encoding="utf-8"))["actions"][0]
    assert committed["status"] == "approved"
    assert committed["escalation_required"] is False
    assert committed["escalation_resolved_by"] == "escalation-reviewer"

    recovered = recovery.recover_interrupted_actions()
    assert recovered == ["free-disk-space"]

    events = json.loads(audit_path.read_text(encoding="utf-8"))
    assert len(events) == 1
    assert events[0]["event"] == "escalation-resolved"
    assert events[0]["resolved_by"] == "escalation-reviewer"
    assert events[0]["recovered"] is True

    assert recovery.recover_interrupted_actions() == []
    events = json.loads(audit_path.read_text(encoding="utf-8"))
    assert len(events) == 1


def test_persistence_failure_does_not_claim_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, "STATE_PATH", tmp_path / "missing.json")
    escalated = {
        "action": "free-disk-space",
        "status": "failed",
        "retry_count": 2,
        "max_retries": 2,
        "escalation_required": True,
    }

    with pytest.raises(FileNotFoundError):
        lifecycle.resolve_escalation(
            escalated,
            principal=ADMIN_PRINCIPAL,
        )

    assert escalated["status"] == "failed"
    assert escalated["escalation_required"] is True
