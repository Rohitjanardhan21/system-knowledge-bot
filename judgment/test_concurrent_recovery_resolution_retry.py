import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import judgment.audit as audit
import judgment.lifecycle as lifecycle
import judgment.recovery as recovery
from judgment.state_lock import state_lock as real_state_lock


def test_concurrent_recovery_resolution_retry_race(
    tmp_path, monkeypatch
):
    state_path = tmp_path / "state" / "latest.json"
    state_path.parent.mkdir(parents=True)

    action = {
        "action": "free-disk-space",
        "status": "executing",
        "execution_mode": "automatic",
        "priority": "high",
        "execution_generation": 1,
        "execution_started_at": (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        ).isoformat(),
        "retry_count": 2,
        "max_retries": 2,
        "escalation_required": True,
        "execution_result": None,
    }

    state_path.write_text(
        json.dumps({"actions": [action]}, indent=2),
        encoding="utf-8",
    )

    audit_path = tmp_path / "audit" / "audit.json"
    lock_path = tmp_path / "state" / "state.lock"

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(recovery, "STATE_PATH", state_path)

    monkeypatch.setattr(
        lifecycle, "state_lock",
        lambda: real_state_lock(lock_path),
    )
    monkeypatch.setattr(
        recovery, "state_lock",
        lambda lock_path=lock_path: real_state_lock(lock_path),
    )
    monkeypatch.setattr(
        recovery, "interprocess_lock",
        lambda path: real_state_lock(path),
    )

    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(
        audit, "AUDIT_TEMP_PATH", audit_path.with_suffix(".tmp")
    )
    monkeypatch.setattr(
        audit, "AUDIT_LOCK_PATH", audit_path.with_suffix(".lock")
    )

    principal = {
        "scope": "admin",
        "_source": "api_key",
        "name": "isolated-test-admin",
    }

    def recovery_worker():
        return recovery.recover_interrupted_actions()

    def resolution_worker():
        return lifecycle.resolve_escalation(
            "free-disk-space",
            principal=principal,
        )

    def retry_worker():
        return lifecycle.retry_failed_action("free-disk-space")

    tasks = (
        [recovery_worker] * 4
        + [resolution_worker] * 4
        + [retry_worker] * 4
    )

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(task) for task in tasks]
        results = [future.result() for future in as_completed(futures)]

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    final_action = next(
        item for item in persisted["actions"]
        if item["action"] == "free-disk-space"
    )
    events = [
        event for event in audit.load_audit()
        if event.get("action") == "free-disk-space"
    ]

    recovery_events = [
        event for event in events
        if event.get("event") == "recovery-interrupted"
    ]
    resolution_events = [
        event for event in events
        if event.get("event") == "escalation-resolved"
    ]
    retry_events = [
        event for event in events
        if event.get("event") == "retry-approved"
    ]

    assert len(recovery_events) <= 1
    assert len(resolution_events) <= 1
    assert len(retry_events) <= 1

    assert final_action["status"] in {
        "failed", "approved", "executing"
    }
    assert final_action["retry_count"] in {0, 2, 3}
    assert final_action["max_retries"] == 2
    assert isinstance(final_action.get("execution_generation"), int)
    assert state_path.exists()
    assert audit_path.exists()
