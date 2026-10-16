from __future__ import annotations

import json
from pathlib import Path

import judgment.audit as audit
import judgment.recovery as recovery
import judgment.state_lock as lock_module


def test_corrupt_state_promotes_valid_temp_and_recovers_once(
    tmp_path: Path,
    monkeypatch,
):
    state_dir = tmp_path / "state"
    audit_dir = tmp_path / "audit"
    state_dir.mkdir()
    audit_dir.mkdir()

    state_path = state_dir / "latest.json"
    temp_path = state_dir / "latest.tmp"
    audit_path = audit_dir / "audit.json"
    lock_path = state_dir / "state.lock"

    action_name = "isolated-corrupt-state-temp-fallback"
    generation = 1

    valid_state = {
        "actions": [
            {
                "action": action_name,
                "priority": "high",
                "execution_mode": "automatic",
                "status": "executing",
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
                "execution_result": None,
                "execution_generation": generation,
                "execution_started_at": "2000-01-01T00:00:00+00:00",
            }
        ]
    }

    # Simulate a crash after writing a valid temp file but before replacing
    # the authoritative state file.
    temp_path.write_text(json.dumps(valid_state, indent=2), encoding="utf-8")
    state_path.write_text('{"actions": [CORRUPTED', encoding="utf-8")
    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(recovery, "STATE_PATH", state_path)
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", audit_path.with_suffix(".tmp"))
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", audit_path.with_suffix(".lock"))

    original_lock = lock_module.state_lock

    def isolated_lock(requested_path=None):
        return original_lock(requested_path or lock_path)

    monkeypatch.setattr(recovery, "state_lock", isolated_lock)

    # 1. Recovery should promote the valid temp candidate and recover the
    # interrupted action.
    recovered_actions = recovery.recover_interrupted_actions()
    assert action_name in recovered_actions

    # 2. Verify the promoted state and recovery result.
    recovered_state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in recovered_state["actions"]
        if item.get("action") == action_name
    )

    assert action["status"] == "failed"
    assert action["execution_result"] == "interrupted-by-restart"
    assert action["execution_generation"] == generation

    # 3. The temporary candidate must have been consumed.
    assert not temp_path.exists()

    # 4. Exactly one matching recovery event must be durable.
    entries = audit.load_audit()
    recovery_events = [
        event for event in entries
        if isinstance(event, dict)
        and event.get("event") == "recovery-interrupted"
        and event.get("action") == action_name
        and event.get("execution_generation") == generation
        and event.get("result") == "interrupted-by-restart"
    ]
    assert len(recovery_events) == 1

    # 5. A second recovery must not recover or audit the same action again.
    second_result = recovery.recover_interrupted_actions()
    assert action_name not in second_result

    entries_after = audit.load_audit()
    matching_events_after = [
        event for event in entries_after
        if isinstance(event, dict)
        and event.get("event") == "recovery-interrupted"
        and event.get("action") == action_name
        and event.get("execution_generation") == generation
        and event.get("result") == "interrupted-by-restart"
    ]
    assert len(matching_events_after) == 1

    # 6. Verify that durable state remains consistent.
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    final_action = next(
        item for item in final_state["actions"]
        if item.get("action") == action_name
    )
    assert final_action["status"] == "failed"
    assert final_action["execution_generation"] == generation
    assert final_action["execution_result"] == "interrupted-by-restart"

    # All test artifacts must reside under pytest's temporary directory.
    assert state_path.is_relative_to(tmp_path)
    assert temp_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)