import json
from contextlib import nullcontext

from judgment import audit, lifecycle


def test_retry_reexecution_audit_order_is_isolated(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    action = {
        "action": "free-disk-space",
        "status": "failed",
        "execution_result": "simulated-execution-failure",
        "retry_count": 0,
        "max_retries": 2,
    }

    state_path.write_text(
        json.dumps({"actions": [action]}, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(
        audit, "AUDIT_TEMP_PATH", state_dir / "audit.tmp"
    )
    monkeypatch.setattr(
        audit, "AUDIT_LOCK_PATH", state_dir / "audit.lock"
    )
    monkeypatch.setattr(lifecycle, "state_lock", nullcontext)

    target = dict(action)

    retry = lifecycle.retry_failed_action(target)
    assert retry["status"] == "approved"
    assert target["status"] == "approved"

    start = lifecycle.begin_execution(target)
    assert start["status"] == "executing"

    complete = lifecycle.complete_execution(
        target,
        success=True,
        result="retry-dry-run-success",
    )
    assert complete["status"] == "executed"

    entries = audit.load_audit()
    events = [
        entry.get("event")
        for entry in entries
        if entry.get("action") == "free-disk-space"
    ]

    assert "retry-approved" in events
    assert "execution-started" in events
    assert "execution-completed" in events

    assert (
        events.index("retry-approved")
        < events.index("execution-started")
        < events.index("execution-completed")
    )

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    stored = persisted["actions"][0]

    assert stored["status"] == "executed"
    assert stored["execution_result"] == "retry-dry-run-success"
    assert (state_dir / "audit.lock").exists()
