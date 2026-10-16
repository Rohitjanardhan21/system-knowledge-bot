from judgment.lifecycle import begin_execution, complete_execution
from state.state_reader import get_action_state


def test_execution_failure_is_persisted_and_requires_explicit_retry(
    isolated_judgment_state,
):
    action = {
        "action": "free-disk-space",
        "priority": "high",
        "status": "approved",
    }

    start = begin_execution(action)
    assert start["status"] == "executing"

    failure = complete_execution(
        action,
        success=False,
        result="simulated-execution-failure",
        execution_generation=start["execution_generation"],
    )

    assert failure["status"] == "failed"
    assert action["execution_result"] == "simulated-execution-failure"
    assert "execution_completed_at" in action

    persisted = get_action_state("free-disk-space")
    assert persisted is not None
    assert persisted["status"] == "failed"
    assert persisted["execution_result"] == "simulated-execution-failure"
    assert "execution_completed_at" in persisted
    assert begin_execution(persisted)["status"] == "blocked"
