import json

import judgment.lifecycle as lifecycle


def test_lifecycle_transitions_persist_and_prevent_reexecution(
    isolated_judgment_state,
):
    state_path, _ = isolated_judgment_state
    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = state["actions"][0]

    assert action["status"] == "approved"

    started = lifecycle.begin_execution(action)
    assert started["status"] == "executing"

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["actions"][0]["status"] == "executing"

    completed = lifecycle.complete_execution(
        action,
        success=True,
        result="dry-run-success",
        execution_generation=started["execution_generation"],
    )
    assert completed["status"] == "executed"

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    final_action = persisted["actions"][0]
    assert final_action["status"] == "executed"
    assert final_action["execution_result"] == "dry-run-success"

    retry = lifecycle.begin_execution(final_action)
    assert retry["status"] == "blocked"
    assert "already been executed" in retry["reason"]
