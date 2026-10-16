import json

from judgment import audit, lifecycle
from judgment.executor import execute_plan
from judgment.state_lock import state_lock
from state import state_reader


def test_full_execution_safety_chain_is_isolated(tmp_path, monkeypatch):
    # Redirect every state, audit, temporary-file, and lock path.
    state_path = tmp_path / "state" / "latest.json"
    audit_path = tmp_path / "state" / "audit.json"
    lock_path = tmp_path / "state" / "state.lock"

    state_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(state_reader, "STATE_PATH", state_path)
    monkeypatch.setattr(state_reader, "AUDIT_PATH", audit_path)

    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", audit_path.with_suffix(".tmp"))
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", audit_path.with_suffix(".lock"))

    monkeypatch.setattr(
        lifecycle,
        "state_lock",
        lambda: state_lock(lock_path),
    )

    action_record = {
        "action": "free-disk-space",
        "status": "failed",
        "retry_count": 0,
        "max_retries": lifecycle.MAX_RETRIES,
        "escalation_required": False,
        "execution_mode": "automatic",
        "priority": 1,
        "execution_result": "simulated-previous-failure",
    }

    state_path.write_text(
        json.dumps({"actions": [action_record]}, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    # 1. Read the isolated failed action.
    action = state_reader.get_action_state("free-disk-space")
    assert action is not None
    assert action["status"] == "failed"

    # 2. Explicit retry approval must be persisted.
    retry = lifecycle.retry_failed_action(action)
    assert retry["status"] == "approved"
    assert retry["retry_count"] == 1

    persisted_after_retry = state_reader.get_action_state("free-disk-space")
    assert persisted_after_retry["status"] == "approved"
    assert persisted_after_retry["retry_count"] == 1

    # 3. Execute in dry-run mode; no real disk cleanup is performed.
    results = execute_plan([action], dry_run=True)
    assert len(results) == 1
    assert results[0]["status"] == "simulated"
    assert results[0]["result"] == "dry-run-success"
    assert results[0]["modified"] is False
    assert results[0]["lifecycle_status"] == "executed"

    # 4. Verify durable terminal state.
    final_action = state_reader.get_action_state("free-disk-space")
    assert final_action["status"] == "executed"
    assert final_action["execution_result"] == "disk-cleanup-simulated"

    # 5. A second execution must be blocked.
    duplicate = execute_plan([final_action], dry_run=True)
    assert len(duplicate) == 1
    assert duplicate[0]["status"] == "blocked"
    assert duplicate[0]["result"] == "already-executed"

    # 6. Verify the durable audit trail.
    entries = audit.load_audit()
    events = [entry.get("event") for entry in entries]

    assert "retry-approved" in events
    assert "execution-started" in events
    assert "execution-completed" in events

    assert sum(event == "execution-completed" for event in events) == 1

    # Every file created by this test must remain under tmp_path.
    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
    assert not audit_path.with_suffix(".tmp").exists()
