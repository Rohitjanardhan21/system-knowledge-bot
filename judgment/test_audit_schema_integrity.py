from datetime import datetime

from judgment.audit import load_audit, record_execution


def test_audit_entries_have_valid_schema_and_order(isolated_judgment_state):
    record_execution(
        {
            "event": "execution-completed",
            "action": "free-disk-space",
            "status": "executed",
            "result": "dry-run-success",
            "execution_generation": 1,
        }
    )
    entries = load_audit()

    assert isinstance(entries, list)
    allowed_events = {
        "execution",
        "execution-failed",
        "retry-blocked",
        "retry-approved",
        "execution-started",
        "execution-completed",
        "recovery-interrupted",
    }
    previous_timestamp = None

    for index, entry in enumerate(entries):
        assert isinstance(entry, dict), f"Entry {index} is not an object."
        assert entry.get("event") in allowed_events
        assert entry.get("timestamp")
        assert entry.get("action")
        assert entry.get("status")
        assert entry.get("result") is not None

        timestamp = datetime.fromisoformat(entry["timestamp"])
        if previous_timestamp is not None:
            assert timestamp >= previous_timestamp
        previous_timestamp = timestamp
