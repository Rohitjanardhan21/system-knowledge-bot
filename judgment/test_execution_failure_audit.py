import json

from judgment import recovery
from judgment.audit import load_audit
from judgment.lifecycle import begin_execution, complete_execution


def test_execution_failure_state_and_audit_match(isolated_judgment_state):
    state_path, _ = isolated_judgment_state
    action = {
        "action": "free-disk-space",
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
    }

    start = begin_execution(action)
    assert start["status"] == "executing"

    failure = complete_execution(
        action,
        success=False,
        result="simulated-handler-failure",
        execution_generation=start["execution_generation"],
    )
    assert failure["status"] == "failed"
    assert failure["result"] == "simulated-handler-failure"

    state = json.loads(recovery.STATE_PATH.read_text(encoding="utf-8"))
    persisted = next(
        item for item in state["actions"]
        if item.get("action") == "free-disk-space"
    )
    assert persisted["status"] == "failed"
    assert persisted["execution_result"] == "simulated-handler-failure"

    matching_events = [
        event for event in load_audit()
        if event.get("action") == "free-disk-space"
        and event.get("event") == "execution-failed"
        and event.get("execution_generation") == start["execution_generation"]
    ]
    assert len(matching_events) == 1
