from judgment.execution import build_execution_plan


def test_execution_plan_reflects_approval_status():
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
        {
            "action": "avoid-heavy-workloads",
            "priority": "high",
            "status": "approved",
            "reason": "System posture is recovery-required.",
            "validation_reason": "Non-destructive.",
        },
    ]

    plan = build_execution_plan(actions)

    assert any(
        item["action"] == "reduce-memory-pressure"
        and item["execution_mode"] == "automatic"
        for item in plan
    )
    assert any(
        item["action"] == "free-disk-space"
        and item["execution_mode"] == "confirmation-required"
        for item in plan
    )
    assert any(
        item["action"] == "avoid-heavy-workloads"
        and item["execution_mode"] == "automatic"
        for item in plan
    )
