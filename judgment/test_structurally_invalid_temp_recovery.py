import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from judgment import audit, recovery
from judgment.state_lock import state_lock as real_state_lock


def test_structurally_invalid_temp_candidate_is_not_promoted(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"
    temp_path = state_path.with_suffix(".tmp")
    audit_path = state_dir / "audit.json"

    # The authoritative file is corrupt, and the temporary candidate
    # is valid JSON but structurally invalid for recovery.
    state_path.write_text("{corrupt-json", encoding="utf-8")
    temp_path.write_text(
        json.dumps({"actions": []}), encoding="utf-8"
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

    recovered = recovery.recover_interrupted_actions()

    assert recovered == []
    assert state_path.read_text(encoding="utf-8") == "{corrupt-json"
    assert temp_path.exists()
    assert json.loads(temp_path.read_text(encoding="utf-8")) == {
        "actions": []
    }
    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
