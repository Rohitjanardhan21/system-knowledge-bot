import json

from judgment.executor import execute_plan
from judgment import recovery


def test_executor_rechecks_preconditions_against_current_facts(
    isolated_judgment_state,
):
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
            "execution_mode": "automatic",
            "status": "approved",
        },
    ]
    healthy_facts = {
        "memory": {"utilization": 65},
        "disk": {"utilization": 70},
    }
    dangerous_facts = {
        "memory": {"utilization": 92},
        "disk": {"utilization": 93},
    }

    healthy_results = execute_plan(
        plan,
        dry_run=True,
        current_facts=healthy_facts,
    )
    assert all(
        result["status"] == "blocked"
        and result["result"] == "precondition-failed"
        for result in healthy_results
    )

    state = json.loads(recovery.STATE_PATH.read_text(encoding="utf-8"))
    for action in state["actions"]:
        action["status"] = "approved"
        action["execution_result"] = None
        action.pop("execution_started_at", None)
        action.pop("execution_completed_at", None)
        action.pop("recovery_reason", None)
    recovery.STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    dangerous_results = execute_plan(
        plan,
        dry_run=True,
        current_facts=dangerous_facts,
    )
    assert all(
        result["status"] == "simulated"
        and result["result"] == "dry-run-success"
        for result in dangerous_results
    )
