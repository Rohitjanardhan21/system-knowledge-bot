from judgment.models import SystemPostureResult
from judgment.action_validator import validate_actions


def test_action_validation_applies_expected_safety_rules():
    actions = [
        {
            "priority": "critical",
            "action": "reduce-memory-pressure",
            "reason": "Memory utilization is critically high.",
        },
        {
            "priority": "high",
            "action": "free-disk-space",
            "reason": "Disk utilization exceeds the safe threshold.",
        },
        {
            "priority": "high",
            "action": "avoid-heavy-workloads",
            "reason": "System posture is recovery-required.",
        },
    ]

    posture = SystemPostureResult(
        posture="recovery-required",
        reasoning="Memory pressure is critical.",
    )

    validated = validate_actions(actions, posture)

    assert any(
        action["action"] == "free-disk-space"
        and action["status"] == "requires-confirmation"
        for action in validated
    )
    assert any(
        action["action"] == "reduce-memory-pressure"
        and action["status"] == "approved"
        for action in validated
    )
    assert any(
        action["action"] == "avoid-heavy-workloads"
        and action["status"] == "approved"
        for action in validated
    )
