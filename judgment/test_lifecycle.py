from judgment.lifecycle import (
    begin_execution,
    can_execute,
    complete_execution,
)


def test_execution_lifecycle_is_idempotent(isolated_judgment_state):
    action = {
        "action": "free-disk-space",
        "priority": "high",
        "status": "requires-confirmation",
    }
    assert not can_execute(action)

    action["status"] = "approved"
    assert can_execute(action)

    started = begin_execution(action)
    assert started["status"] == "executing"
    assert not can_execute(action)

    completed = complete_execution(
        action,
        success=True,
        result="dry-run-success",
        execution_generation=started["execution_generation"],
    )
    assert completed["status"] == "executed"
    assert not can_execute(action)

    retry = begin_execution(action)
    assert retry["status"] == "blocked"
    assert "already been executed" in retry["reason"]
