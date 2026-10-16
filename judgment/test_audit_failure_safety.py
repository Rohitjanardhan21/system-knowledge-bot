import json
from pathlib import Path

import pytest

import judgment.audit as audit
import judgment.lifecycle as lifecycle
from judgment.state_lock import state_lock as real_state_lock


def test_audit_failure_never_claims_execution_success(tmp_path, monkeypatch):
    state_path = tmp_path / "state" / "latest.json"
    state_path.parent.mkdir(parents=True)

    action = {
        "action": "free-disk-space",
        "status": "approved",
        "execution_mode": "automatic",
        "execution_generation": 0,
        "execution_result": None,
    }
    state_path.write_text(
        json.dumps({"actions": [action]}, indent=2),
        encoding="utf-8",
    )

    audit_path = tmp_path / "audit" / "audit.json"
    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(
        lifecycle,
        "state_lock",
        lambda: real_state_lock(tmp_path / "state" / "state.lock"),
    )
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", audit_path.with_suffix(".tmp"))
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", audit_path.with_suffix(".lock"))

    def failing_audit(*args, **kwargs):
        raise RuntimeError("simulated-audit-write-failure")

    monkeypatch.setattr(lifecycle, "record_execution", failing_audit)

    with pytest.raises(RuntimeError, match="simulated-audit-write-failure"):
        lifecycle.begin_execution(action)

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    stored = next(
        item for item in persisted["actions"]
        if item["action"] == "free-disk-space"
    )

    assert stored["status"] in {"approved", "executing", "failed"}
    assert stored["status"] != "executed"
    assert stored["execution_generation"] == 1
    assert not audit_path.exists()
