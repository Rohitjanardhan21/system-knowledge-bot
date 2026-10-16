import json
from contextlib import contextmanager

from judgment import audit
from judgment.state_lock import state_lock as real_state_lock


def test_execution_audit_persists_results_in_isolated_state(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    audit_path = state_dir / "audit.json"
    audit_temp_path = state_dir / "audit.tmp"
    audit_lock_path = state_dir / "audit.lock"

    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", audit_temp_path)
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", audit_lock_path)

    results = [
        {
            "action": "reduce-memory-pressure",
            "priority": "critical",
            "execution_mode": "automatic",
            "status": "simulated",
            "result": "dry-run-success",
        },
        {
            "action": "free-disk-space",
            "priority": "high",
            "execution_mode": "confirmation-required",
            "status": "blocked",
            "result": "confirmation-required",
        },
    ]

    recorded = audit.record_execution(results)

    assert len(recorded) == 2
    assert any(
        entry["action"] == "reduce-memory-pressure"
        and entry["status"] == "simulated"
        for entry in recorded
    )
    assert any(
        entry["action"] == "free-disk-space"
        and entry["status"] == "blocked"
        for entry in recorded
    )

    loaded = audit.load_audit()
    assert len(loaded) == 2
    assert any(
        entry["action"] == "reduce-memory-pressure"
        and entry["status"] == "simulated"
        and entry["result"] == "dry-run-success"
        for entry in loaded
    )
    assert any(
        entry["action"] == "free-disk-space"
        and entry["status"] == "blocked"
        and entry["result"] == "confirmation-required"
        for entry in loaded
    )

    assert audit_path.is_relative_to(tmp_path)
    assert audit_temp_path.is_relative_to(tmp_path)
    assert audit_lock_path.is_relative_to(tmp_path)
