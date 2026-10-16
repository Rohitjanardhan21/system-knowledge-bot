import json
from contextlib import contextmanager

from judgment import audit, recovery
from judgment.state_lock import state_lock as real_state_lock


def test_executed_identity_conflict_candidate_is_not_promoted(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    temp_path = state_path.with_suffix(".tmp")
    audit_path = state_dir / "audit.json"

    # The authoritative state is unreadable.
    state_path.write_text("{corrupt-json", encoding="utf-8")

    # The candidate uses a different action identity and an "executed"
    # status, which does not qualify under the current recovery validator.
    candidate = {
        "actions": [{
            "action": "restart-service",
            "status": "executed",
            "execution_result": "identity-conflict-success",
        }]
    }
    temp_path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(recovery, "STATE_PATH", state_path)
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", state_dir / "audit.tmp")
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", state_dir / "audit.lock")

    @contextmanager
    def isolated_state_lock(lock_path=None):
        path = lock_path if lock_path is not None else state_dir / "state.lock"
        with real_state_lock(path):
            yield

    monkeypatch.setattr(recovery, "state_lock", isolated_state_lock)

    recovered = recovery.recover_interrupted_actions()

    assert recovered == []
    assert state_path.read_text(encoding="utf-8") == "{corrupt-json"
    assert temp_path.exists()

    stored_candidate = json.loads(temp_path.read_text(encoding="utf-8"))
    assert stored_candidate["actions"][0]["action"] == "restart-service"
    assert stored_candidate["actions"][0]["status"] == "executed"
