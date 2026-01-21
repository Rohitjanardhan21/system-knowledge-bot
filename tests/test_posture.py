from judgment.posture import resolve_posture
from judgment.models import Judgment, Evidence


def test_posture_idle_when_no_judgments():
    posture = resolve_posture([])
    assert posture.posture == "idle-capable"


def test_posture_constrained():
    judgments = [
        Judgment(
            state="constrained",
            confidence=0.8,
            impact_scope="local",
            urgency="act-soon",
            recommended_posture="delay",
            evidence=[
                Evidence(
                    source="cpu",
                    observation="CPU usage high",
                    baseline="40%",
                    deviation="+35%"
                )
            ]
        )
    ]

    posture = resolve_posture(judgments)
    assert posture.posture == "capacity-constrained"
