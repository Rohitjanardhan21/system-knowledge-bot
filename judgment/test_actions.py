from judgment.models import Judgment, Evidence, SystemPostureResult
from judgment.actions import recommend_actions


def test_action_recommendations_include_capacity_responses():
    judgments = [
        Judgment(
            state="constrained",
            confidence=0.95,
            evidence=[
                Evidence(
                    source="system.storage",
                    observation="Disk utilization is 93.8%",
                    baseline="Disk utilization below 90%",
                    deviation="Disk utilization exceeds 90% threshold",
                )
            ],
            impact_scope="system-wide",
            urgency="act-soon",
            recommended_posture="investigate",
        )
    ]

    posture = SystemPostureResult(
        posture="capacity-constrained",
        reasoning="Disk capacity is constrained.",
    )

    actions = recommend_actions(judgments, posture)

    assert any(
        action["action"] == "free-disk-space"
        for action in actions
    )
    assert any(
        action["action"] == "avoid-heavy-workloads"
        for action in actions
    )
