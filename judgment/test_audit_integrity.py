import json

import judgment.audit as audit
import judgment.lifecycle as lifecycle
from judgment.executor import execute_plan
from judgment.state_lock import state_lock as real_state_lock


def test_execution_audit_integrity_and_explicit_retry(tmp_path, monkeypatch):
    state_path = tmp_path / "state" / "latest.json"
    state_path.parent.mkdir(parents=True)

    action = {
        "action": "free-disk-space",
        "status": "approved",
        "execution_mode": "automatic",
        "priority": "high",
        "execution_generation": 0,
        "retry_count": 0,
        "max_retries": 3,
        "execution_result": None,
    }

    state_path.write_text(
        json.dumps({"actions": [action]}, indent=2),
        encoding="utf-8",
    )

    audit_path = tmp_path / "audit" / "audit.json"

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(
        lifecycle,
        "state_lock",
        lambda: real_state_lock(tmp_path / "state" / "state.lock"),
    )
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", audit_path.with_suffix(".tmp"))
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", audit_path.with_suffix(".lock"))

    started = lifecycle.begin_execution(action)
    assert started["status"] == "executing"

    events = audit.load_audit()
    assert any(event.get("event") == "execution-started" for event in events)

    completed = lifecycle.complete_execution(
        action,
        success=True,
        result="audit-integrity-success",
        execution_generation=started["execution_generation"],
    )
    assert completed["status"] == "executed"
    assert completed["result"] == "audit-integrity-success"

    events = audit.load_audit()
    assert any(
        event.get("event") == "execution-completed"
        and event.get("result") == "audit-integrity-success"
        for event in events
    )

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    stored = next(item for item in persisted["actions"]
                  if item["action"] == "free-disk-space")
    assert stored["status"] == "executed"
    assert stored["execution_result"] == "audit-integrity-success"

    already_executed = execute_plan(
        [{
            **stored,
            "execution_mode": "automatic",
            "priority": "high",
        }],
        dry_run=True,
    )
    assert already_executed[0]["result"] == "already-executed"

    events_after_duplicate = audit.load_audit()
    assert not any(
        event.get("result") == "already-executed"
        and event.get("status") == "executed"
        for event in events_after_duplicate
    )

    stored["status"] = "failed"
    stored["execution_result"] = "simulated-failure"
    state_path.write_text(
        json.dumps(persisted, indent=2),
        encoding="utf-8",
    )

    retry_blocked = execute_plan(
        [{
            **stored,
            "execution_mode": "automatic",
            "priority": "high",
        }],
        dry_run=True,
    )
    assert retry_blocked[0]["result"] == "retry-required"

    retry = lifecycle.retry_failed_action(stored)
    assert retry["status"] == "approved"

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    stored_after_retry = next(
        item for item in persisted["actions"]
        if item["action"] == "free-disk-space"
    )
    assert stored_after_retry["status"] == "approved"

    events = audit.load_audit()
    event_names = [event.get("event") for event in events]
    assert "execution-started" in event_names
    assert "execution-completed" in event_names
    assert "retry-approved" in event_names

    retry_events = [
        event for event in events
        if event.get("event") == "retry-approved"
    ]
    assert retry_events
    assert retry_events[-1].get("status") == "approved"

    assert len(audit.load_audit()) >= len(events)
