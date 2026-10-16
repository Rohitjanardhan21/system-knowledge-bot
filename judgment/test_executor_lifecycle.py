import json

from judgment.executor import execute_plan


def test_executor_lifecycle_enforces_confirmation_and_dry_run(
    isolated_judgment_state,
):
    state_path, _ = isolated_judgment_state
    plan = [
        {
            "action": "reduce-memory-pressure",
            "priority": "critical",
            "execution_mode": "automatic",
            "status": "approved",
        },
        {
            "action": "free-disk-space",
            "priority": "high",
            "execution_mode": "confirmation-required",
            "status": "requires-confirmation",
        },
    ]

    results = execute_plan(plan, dry_run=True)
    assert any(
        result["action"] == "reduce-memory-pressure"
        and result["status"] == "simulated"
        and result["result"] == "dry-run-success"
        and result["lifecycle_status"] == "executed"
        for result in results
    )
    assert any(
        result["action"] == "free-disk-space"
        and result["status"] == "blocked"
        and result["result"] == "confirmation-required"
        for result in results
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    reduce_memory = next(
        action for action in state["actions"]
        if action["action"] == "reduce-memory-pressure"
    )
    reduce_memory["status"] = "approved"
    reduce_memory.pop("execution_started_at", None)
    reduce_memory.pop("execution_completed_at", None)
    reduce_memory.pop("execution_result", None)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    real_results = execute_plan(
        [
            {
                "action": "reduce-memory-pressure",
                "priority": "critical",
                "execution_mode": "automatic",
                "status": "approved",
            }
        ],
        dry_run=False,
    )
    assert real_results[0]["status"] == "failed"
    assert real_results[0]["result"] == "real-execution-disabled"
