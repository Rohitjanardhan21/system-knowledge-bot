from judgment.execution import build_execution_plan
from judgment.executor import execute_plan


def test_judgment_to_execution_chain_rechecks_confirmation_and_preconditions(
    isolated_judgment_state,
):
    actions = [
        {
            "action": "reduce-memory-pressure",
            "priority": "critical",
            "status": "approved",
            "reason": "Memory utilization is critically high.",
            "validation_reason": "Non-destructive.",
        },
        {
            "action": "free-disk-space",
            "priority": "high",
            "status": "requires-confirmation",
            "reason": "Disk utilization exceeds the safe threshold.",
            "validation_reason": "May modify system data.",
        },
    ]
    plan = build_execution_plan(actions)

    assert plan[0]["status"] == "approved"
    assert plan[0]["execution_mode"] == "automatic"
    assert plan[1]["status"] == "requires-confirmation"
    assert plan[1]["execution_mode"] == "confirmation-required"

    results = execute_plan(
        plan,
        dry_run=True,
        current_facts={
            "memory": {"utilization": 92},
            "disk": {"utilization": 93},
        },
    )

    assert results[0]["status"] == "simulated"
    assert results[0]["result"] == "dry-run-success"
    assert results[0]["lifecycle_status"] == "executed"
    assert results[1]["status"] == "blocked"
    assert results[1]["result"] == "confirmation-required"
