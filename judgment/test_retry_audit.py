from judgment.audit import load_audit, record_execution


def test_lifecycle_audit_events_are_append_only(isolated_judgment_state):
    _, audit_path = isolated_judgment_state
    events = [
        {
            "action": "free-disk-space",
            "status": "failed",
            "result": "interrupted-by-restart",
            "event": "recovery-interrupted",
        },
        {
            "action": "free-disk-space",
            "status": "blocked",
            "result": "precondition-failed",
            "event": "retry-blocked",
        },
        {
            "action": "free-disk-space",
            "status": "approved",
            "result": "retry-approved",
            "event": "retry-approved",
        },
        {
            "action": "free-disk-space",
            "status": "executing",
            "result": "execution-started",
            "event": "execution-started",
        },
        {
            "action": "free-disk-space",
            "status": "executed",
            "result": "dry-run-success",
            "event": "execution-completed",
        },
    ]

    before = load_audit()
    for event in events:
        record_execution(event)
    after = load_audit()

    assert len(after) == len(before) + len(events)
    new_entries = after[len(before):]
    for event in events:
        assert any(
            entry.get("action") == event["action"]
            and entry.get("status") == event["status"]
            and entry.get("result") == event["result"]
            and entry.get("event") == event["event"]
            for entry in new_entries
        ), f"Missing audit event: {event['event']}"

    assert audit_path.exists()
