import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from judgment import audit, lifecycle, recovery
from judgment.state_lock import state_lock as real_state_lock


def test_stale_worker_completion_is_rejected_after_recovery(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    action = {
        "action": "free-disk-space",
        "status": "approved",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
    }

    state_path.write_text(
        json.dumps({"actions": [action]}, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
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
            lock_path
            if lock_path is not None
            else state_dir / "state.lock"
        )
        with real_state_lock(path):
            yield

    monkeypatch.setattr(lifecycle, "state_lock", isolated_state_lock)
    monkeypatch.setattr(recovery, "state_lock", isolated_state_lock)

    # Worker A starts and receives its original generation.
    worker_a = lifecycle.begin_execution(action)
    assert worker_a["status"] == "executing"
    generation_a = worker_a["execution_generation"]

    # Simulate a stale worker by aging its durable execution timestamp.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["actions"][0]["execution_started_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    recovered = recovery.recover_interrupted_actions()
    assert "free-disk-space" in recovered

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["actions"][0]["status"] == "failed"

    # Explicit retry authorizes Worker B with a new generation.
    retry = lifecycle.retry_failed_action("free-disk-space")
    assert retry["status"] == "approved"
    assert retry["retry_count"] == 1

    worker_b = lifecycle.begin_execution("free-disk-space")
    assert worker_b["status"] == "executing"
    generation_b = worker_b["execution_generation"]
    assert generation_b > generation_a

    # Worker B completes successfully.
    completed = lifecycle.complete_execution(
        {"action": "free-disk-space"},
        success=True,
        result="worker-b-success",
        execution_generation=generation_b,
    )
    assert completed["status"] == "executed"

    # Worker A attempts completion using its original generation.
    stale = lifecycle.complete_execution(
        {"action": "free-disk-space"},
        success=True,
        result="STALE-WORKER-A-COMPLETION",
        execution_generation=generation_a,
    )
    assert stale["status"] == "blocked"
    assert stale["result"] == "stale-execution-generation"

    # A stale worker must not be allowed to perform a side effect either.
    side_effect_called = []

    stale_effect = lifecycle.run_execution_side_effect(
        {"action": "free-disk-space"},
        generation_a,
        lambda: side_effect_called.append(True),
    )
    assert stale_effect["status"] == "blocked"
    assert stale_effect["result"] == "stale-execution-generation"
    assert side_effect_called == []

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    final_action = persisted["actions"][0]

    assert final_action["status"] == "executed"
    assert final_action["execution_result"] == "worker-b-success"
    assert final_action["execution_generation"] == generation_b
    assert final_action["retry_count"] == 1

    events = [
        entry for entry in audit.load_audit()
        if entry.get("action") == "free-disk-space"
    ]
    assert any(
        entry.get("event") == "recovery-interrupted"
        for entry in events
    )
    assert any(
        entry.get("event") == "execution-completed"
        and entry.get("result") == "worker-b-success"
        and entry.get("execution_generation") == generation_b
        for entry in events
    )

    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
