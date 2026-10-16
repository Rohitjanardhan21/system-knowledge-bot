from judgment.audit import load_audit, record_execution


def test_record_execution_preserves_custom_lifecycle_events(
    isolated_judgment_state,
):
    before = load_audit()

    recorded = record_execution(
        {
            "event": "retry-approved",
            "action": "audit-debug",
            "status": "approved",
            "result": "retry-approved",
        }
    )

    after = load_audit()

    assert len(after) == len(before) + 1
    assert recorded[0]["event"] == "retry-approved"
    assert after[-1]["action"] == "audit-debug"
