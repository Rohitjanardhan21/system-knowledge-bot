import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from judgment import audit, lifecycle, recovery
from judgment.state_lock import state_lock as real_state_lock


def test_stale_worker_cannot_complete_newer_generation(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    sandbox = tmp_path / "sandbox"
    state_dir.mkdir()
    sandbox.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"
    file_a = sandbox / "cleanup_a.tmp"
    file_b = sandbox / "cleanup_b.tmp"
    file_a.write_text("temporary data", encoding="utf-8")
    file_b.write_text("temporary data", encoding="utf-8")

    action = {
        "action": "free-disk-space",
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_result": None,
    }
    state_path.write_text(
        json.dumps({"actions": [action]}, indent=2), encoding="utf-8"
    )
    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(recovery, "STATE_PATH", state_path)
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", state_dir / "audit.tmp")
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", state_dir / "audit.lock")

    @contextmanager
    def isolated_state_lock(lock_path=None):
        path = lock_path if lock_path is not None else state_dir / "state.lock"
        with real_state_lock(path):
            yield

    monkeypatch.setattr(lifecycle, "state_lock", isolated_state_lock)
    monkeypatch.setattr(recovery, "state_lock", isolated_state_lock)

    # Worker A starts and performs one simulated side effect in the sandbox.
    worker_a = lifecycle.begin_execution("free-disk-space")
    assert worker_a["status"] == "executing"
    generation_a = worker_a["execution_generation"]

    effect_a = lifecycle.run_execution_side_effect(
        {"action": "free-disk-space"},
        generation_a,
        file_a.unlink,
    )
    assert effect_a["status"] == "allowed"
    assert not file_a.exists()
    assert file_b.exists()

    # Simulate a crash and let recovery invalidate Worker A.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["actions"][0]["execution_started_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    recovered = recovery.recover_interrupted_actions()
    assert "free-disk-space" in recovered

    recovered_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert recovered_state["actions"][0]["status"] == "failed"
    assert (
        recovered_state["actions"][0]["execution_result"]
        == "interrupted-by-restart"
    )

    retry = lifecycle.retry_failed_action("free-disk-space")
    assert retry["status"] == "approved"
    assert retry["retry_count"] == 1

    # Worker B receives a new generation.
    worker_b = lifecycle.begin_execution("free-disk-space")
    assert worker_b["status"] == "executing"
    generation_b = worker_b["execution_generation"]
    assert generation_b > generation_a

    # Worker A must not complete Worker B's execution.
    stale = lifecycle.complete_execution(
        {"action": "free-disk-space"},
        success=True,
        result="STALE-WORKER-A-SUCCESS",
        execution_generation=generation_a,
    )
    assert stale["status"] == "blocked"
    assert stale["result"] == "stale-execution-generation"

    current = json.loads(state_path.read_text(encoding="utf-8"))
    assert current["actions"][0]["status"] == "executing"

    # Worker B completes with its own generation.
    completed = lifecycle.complete_execution(
        {"action": "free-disk-space"},
        success=True,
        result="WORKER-B-SUCCESS",
        execution_generation=generation_b,
    )
    assert completed["status"] == "executed"

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    final_action = final_state["actions"][0]
    assert final_action["status"] == "executed"
    assert final_action["execution_result"] == "WORKER-B-SUCCESS"
    assert final_action["execution_generation"] == generation_b
    assert final_action["retry_count"] == 1

    # The sandbox records only the intended Worker A side effect.
    assert not file_a.exists()
    assert file_b.exists()

    events = [
        event for event in audit.load_audit()
        if event.get("action") == "free-disk-space"
    ]
    observed = [event.get("event") for event in events]
    assert "execution-started" in observed
    assert "recovery-interrupted" in observed
    assert "retry-approved" in observed
    assert any(
        event.get("event") == "execution-completed"
        and event.get("result") == "WORKER-B-SUCCESS"
        and event.get("execution_generation") == generation_b
        for event in events
    )
