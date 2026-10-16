import json
from contextlib import contextmanager

from judgment import audit, recovery
from judgment.state_lock import state_lock as real_state_lock


def test_stronger_temp_state_does_not_replace_valid_authoritative_state(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"
    temp_path = state_path.with_suffix(".tmp")
    audit_path = state_dir / "audit.json"

    authoritative = {
        "actions": [{
            "action": "free-disk-space",
            "status": "failed",
            "retry_count": 1,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": "interrupted-by-restart",
        }]
    }
    stronger_temp = {
        "actions": [{
            "action": "free-disk-space",
            "status": "failed",
            "retry_count": 2,
            "max_retries": 2,
            "escalation_required": True,
            "execution_result": "interrupted-by-restart",
        }]
    }

    state_path.write_text(
        json.dumps(authoritative, indent=2), encoding="utf-8"
    )
    temp_path.write_text(
        json.dumps(stronger_temp, indent=2), encoding="utf-8"
    )
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

    before = json.loads(state_path.read_text(encoding="utf-8"))
    assert before["actions"][0]["retry_count"] == 1
    assert before["actions"][0]["escalation_required"] is False

    recovery.recover_interrupted_actions()

    after = json.loads(state_path.read_text(encoding="utf-8"))
    stored = after["actions"][0]

    assert stored["action"] == "free-disk-space"
    assert stored["retry_count"] == 1
    assert stored["escalation_required"] is False

    # Recovery removes an orphaned temp file after using valid authoritative state.
    assert not temp_path.exists()
    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
