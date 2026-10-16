import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from judgment import audit, execution, lifecycle, recovery
from judgment.state_lock import state_lock as real_state_lock


def test_second_escalation_crash_recovery_is_isolated(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    action = {
        "action": "free-disk-space",
        "status": "failed",
        "retry_count": 2,
        "max_retries": 2,
        "escalation_required": True,
        "execution_result": "second-escalation",
    }

    state_path.write_text(
        json.dumps({"actions": [action]}, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(execution, "STATE_PATH", state_path)
    monkeypatch.setattr(recovery, "STATE_PATH", state_path)

    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(
        audit, "AUDIT_TEMP_PATH", state_dir / "audit.tmp"
    )
    monkeypatch.setattr(
        audit, "AUDIT_LOCK_PATH", state_dir / "audit.lock"
    )

    @contextmanager
    def isolated_state_lock(lock_path=None):
        path = (
            Path(lock_path)
            if lock_path is not None
            else state_dir / "state.lock"
        )
        with real_state_lock(path):
            yield

    monkeypatch.setattr(lifecycle, "state_lock", isolated_state_lock)
    monkeypatch.setattr(recovery, "state_lock", isolated_state_lock)

    principal = {
        "scope": "admin",
        "_source": "api_key",
        "name": "isolated-test-admin",
    }

    # Resolve the exhausted escalation and reset the retry budget.
    resolution = lifecycle.resolve_escalation(
        "free-disk-space", principal=principal
    )
    assert resolution["status"] == "approved"
    assert resolution["retry_count"] == 0
    assert resolution["escalation_required"] is False

    # First execution fails.
    assert execution.execute_action("free-disk-space")["status"] == "executing"
    first_failure = execution.execute_action(
        "free-disk-space",
        result="second-cycle-failure",
        complete=True,
        success=False,
    )
    assert first_failure["status"] == "failed"

    # Retry 1 is approved and fails.
    retry_one = lifecycle.retry_failed_action("free-disk-space")
    assert retry_one["status"] == "approved"
    assert retry_one["retry_count"] == 1

    assert execution.execute_action("free-disk-space")["status"] == "executing"
    failure_one = execution.execute_action(
        "free-disk-space",
        result="second-cycle-retry-failure",
        complete=True,
        success=False,
    )
    assert failure_one["status"] == "failed"

    # Retry 2 is approved and fails.
    retry_two = lifecycle.retry_failed_action("free-disk-space")
    assert retry_two["status"] == "approved"
    assert retry_two["retry_count"] == 2

    assert execution.execute_action("free-disk-space")["status"] == "executing"
    final_failure = execution.execute_action(
        "free-disk-space",
        result="second-cycle-final-retry-failure",
        complete=True,
        success=False,
    )
    assert final_failure["status"] == "failed"

    # Exhaustion must re-escalate the action.
    exhausted = lifecycle.retry_failed_action("free-disk-space")
    assert exhausted["status"] == "blocked"
    assert exhausted["retry_count"] == 2
    assert exhausted["escalation_required"] is True

    # Simulate a crash during execution with a stale timestamp.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    target = state["actions"][0]
    target["status"] = "executing"
    target["execution_started_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    recovered = recovery.recover_interrupted_actions()
    assert "free-disk-space" in recovered

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    target = persisted["actions"][0]

    assert target["status"] == "failed"
    assert target["execution_result"] == "interrupted-by-restart"
    assert target["retry_count"] == 2
    assert target["escalation_required"] is True

    # Recovery must not restore retry authority.
    post_recovery = lifecycle.retry_failed_action("free-disk-space")
    assert post_recovery["status"] == "blocked"
    assert post_recovery["retry_count"] == 2
    assert post_recovery["escalation_required"] is True

    events = [
        entry for entry in audit.load_audit()
        if entry.get("action") == "free-disk-space"
    ]

    assert sum(
        entry.get("event") == "escalation-resolved"
        for entry in events
    ) == 1

    assert sum(
        entry.get("event") == "recovery-interrupted"
        and entry.get("result") == "interrupted-by-restart"
        for entry in events
    ) == 1

    assert any(entry.get("event") == "retry-approved" for entry in events)
    assert any(entry.get("event") == "retry-blocked" for entry in events)

    # Every file touched by the test must remain inside tmp_path.
    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
