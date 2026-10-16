from judgment.audit import load_audit, record_execution


def test_record_execution_appends_lifecycle_event(isolated_judgment_state):
    before = load_audit()

    recorded = record_execution(
        {
            "event": "execution-completed",
            "action": "AUDIT-DIAGNOSTIC",
            "status": "executed",
            "result": "TEST",
            "execution_generation": 999,
        }
    )

    after = load_audit()
    matches = [
        event
        for event in after
        if event.get("action") == "AUDIT-DIAGNOSTIC"
    ]

    assert len(after) == len(before) + 1
    assert matches == recorded
