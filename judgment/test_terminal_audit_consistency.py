import json
from pathlib import Path

from judgment import audit


def test_terminal_state_has_matching_audit_event(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    state = {
        "actions": [{
            "action": "free-disk-space",
            "status": "failed",
            "execution_result": "interrupted-by-restart",
        }]
    }
    events = [
        {
            "event": "action-created",
            "action": "free-disk-space",
            "status": "approved",
            "result": "approved",
        },
        {
            "event": "recovery-interrupted",
            "action": "free-disk-space",
            "status": "failed",
            "result": "interrupted-by-restart",
        },
    ]

    state_path.write_text(json.dumps(state), encoding="utf-8")
    audit_path.write_text(json.dumps(events), encoding="utf-8")

    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", state_dir / "audit.tmp")
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", state_dir / "audit.lock")

    loaded_state = json.loads(state_path.read_text(encoding="utf-8"))
    loaded_audit = audit.load_audit()

    target = next(
        item for item in loaded_state["actions"]
        if item.get("action") == "free-disk-space"
    )
    assert target["status"] in {"executed", "failed", "rejected"}

    action_events = [
        event for event in loaded_audit
        if event.get("action") == target["action"]
    ]
    assert action_events

    if target["status"] == "executed":
        matching = [
            event for event in action_events
            if event.get("event") == "execution-completed"
            and event.get("status") == "executed"
        ]
    elif target["status"] == "failed":
        matching = [
            event for event in action_events
            if event.get("event") in {
                "execution-failed", "recovery-interrupted"
            }
            and event.get("status") == "failed"
        ]
    else:
        matching = [
            event for event in action_events
            if event.get("status") == target["status"]
        ]

    assert matching, (
        f"No terminal audit event matches state '{target['status']}'"
    )
    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
