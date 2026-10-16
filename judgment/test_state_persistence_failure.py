import json

import pytest

from judgment import audit, lifecycle
from judgment.state_lock import state_lock as real_state_lock


def test_completion_persistence_failure_does_not_record_success(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    initial_action = {
        "action": "free-disk-space",
        "status": "approved",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_result": None,
    }
    state_path.write_text(
        json.dumps({"actions": [initial_action]}, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", state_dir / "audit.tmp")
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", state_dir / "audit.lock")

    monkeypatch.setattr(
        lifecycle,
        "state_lock",
        lambda: real_state_lock(state_dir / "state.lock"),
    )

    started = lifecycle.begin_execution("free-disk-space")
    assert started["status"] == "executing"
    generation = started["execution_generation"]

    # Confirm the start state is durably persisted before injecting failure.
    before_failure = json.loads(state_path.read_text(encoding="utf-8"))
    stored_before = before_failure["actions"][0]
    assert stored_before["status"] == "executing"
    assert stored_before["execution_generation"] == generation

    events_before = [
        event for event in audit.load_audit()
        if event.get("action") == "free-disk-space"
    ]
    assert any(event.get("event") == "execution-started" for event in events_before)

    def failing_persist(_action):
        raise RuntimeError("simulated-state-write-failure")

    monkeypatch.setattr(lifecycle, "_persist_action", failing_persist)

    with pytest.raises(
        RuntimeError, match="simulated-state-write-failure"
    ):
        lifecycle.complete_execution(
            "free-disk-space",
            success=True,
            result="simulated-success",
            execution_generation=generation,
        )

    # Re-read from disk: the failed write must not manufacture durable success.
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    stored_after = persisted["actions"][0]
    assert stored_after["status"] == "executing"
    assert stored_after.get("execution_result") is None
    assert stored_after["execution_generation"] == generation

    events_after = [
        event for event in audit.load_audit()
        if event.get("action") == "free-disk-space"
    ]
    assert not any(
        event.get("event") == "execution-completed"
        and event.get("result") == "simulated-success"
        for event in events_after
    )

    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
