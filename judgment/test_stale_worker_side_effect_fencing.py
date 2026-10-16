import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from judgment import audit, lifecycle, recovery
from judgment.state_lock import state_lock as real_state_lock


def test_stale_worker_side_effect_is_blocked(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    sandbox = tmp_path / "sandbox"
    state_dir.mkdir()
    sandbox.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"
    file_a = sandbox / "worker_a.tmp"
    file_b = sandbox / "worker_b.tmp"
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

    # Worker A starts with its own generation.
    worker_a = lifecycle.begin_execution("free-disk-space")
    assert worker_a["status"] == "executing"
    generation_a = worker_a["execution_generation"]

    # Simulate a crash by aging the durable execution timestamp.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["actions"][0]["execution_started_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    recovered = recovery.recover_interrupted_actions()
    assert "free-disk-space" in recovered

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["actions"][0]["status"] == "failed"
    assert (
        state["actions"][0]["execution_result"]
        == "interrupted-by-restart"
    )

    # Explicit retry and Worker B's newer generation.
    retry = lifecycle.retry_failed_action("free-disk-space")
    assert retry["status"] == "approved"
    assert retry["retry_count"] == 1

    worker_b = lifecycle.begin_execution("free-disk-space")
    assert worker_b["status"] == "executing"
    generation_b = worker_b["execution_generation"]
    assert generation_b > generation_a

    # A stale callback must be rejected without touching the file.
    stale_callback_calls = []

    stale_result = lifecycle.run_execution_side_effect(
        {"action": "free-disk-space"},
        generation_a,
        lambda: (stale_callback_calls.append(True), file_a.unlink()),
    )
    assert stale_result["status"] == "blocked"
    assert stale_result["result"] == "stale-execution-generation"
    assert stale_callback_calls == []
    assert file_a.exists()
    assert file_b.exists()

    # The current generation may perform sandbox-only side effects.
    result_a = lifecycle.run_execution_side_effect(
        {"action": "free-disk-space"}, generation_b, file_a.unlink
    )
    result_b = lifecycle.run_execution_side_effect(
        {"action": "free-disk-space"}, generation_b, file_b.unlink
    )
    assert result_a["status"] == "allowed"
    assert result_b["status"] == "allowed"
    assert not file_a.exists()
    assert not file_b.exists()

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

    events = [
        event for event in audit.load_audit()
        if event.get("action") == "free-disk-space"
    ]
    observed = [event.get("event") for event in events]
    assert "recovery-interrupted" in observed
    assert "retry-approved" in observed
    assert any(
        event.get("event") == "execution-completed"
        and event.get("result") == "WORKER-B-SUCCESS"
        for event in events
    )
