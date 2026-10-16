from judgment.execution import build_execution_plan


def test_execution_plan_keeps_confirmation_actions_blocked():
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
    automatic = [
        item for item in plan
        if item["execution_mode"] == "automatic"
    ]
    confirmation_required = [
        item for item in plan
        if item["execution_mode"] == "confirmation-required"
    ]

    assert len(automatic) == 2
    assert len(confirmation_required) == 1
    assert {item["action"] for item in automatic} == {
        "reduce-memory-pressure",
        "avoid-heavy-workloads",
    }
    assert confirmation_required[0]["action"] == "free-disk-space"
