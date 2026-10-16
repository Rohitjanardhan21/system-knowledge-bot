from judgment.executor import execute_plan


def test_executor_enforces_modes_and_dry_run(isolated_judgment_state):
    plan = [
        {
            "action": "reduce-memory-pressure",
            "priority": "critical",
            "execution_mode": "automatic",
        },
        {
            "action": "free-disk-space",
            "priority": "high",
            "execution_mode": "confirmation-required",
        },
        {
            "action": "avoid-heavy-workloads",
            "priority": "high",
            "execution_mode": "automatic",
        },
    ]

    results = execute_plan(plan, dry_run=True)

    assert len(results) == 3
    assert results[0]["status"] == "simulated"
    assert results[0]["result"] == "dry-run-success"
    assert results[1]["status"] == "blocked"
    assert results[1]["result"] == "confirmation-required"
    assert results[2]["status"] == "simulated"
    assert results[2]["result"] == "dry-run-success"
