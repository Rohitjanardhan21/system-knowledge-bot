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


def test_posture_prefers_constrained_over_higher_confidence_degraded():
    judgments = [
        Judgment(
            state="degraded",
            confidence=0.95,
            impact_scope="local",
            urgency="observe",
            recommended_posture="continue",
            evidence=[
                Evidence(
                    source="cpu",
                    observation="CPU moderately elevated",
                    baseline="40%",
                    deviation="+15%"
                )
            ]
        ),
        Judgment(
            state="constrained",
            confidence=0.80,
            impact_scope="system-wide",
            urgency="act-soon",
            recommended_posture="delay",
            evidence=[
                Evidence(
                    source="memory",
                    observation="Memory critically constrained",
                    baseline="50%",
                    deviation="+40%"
                )
            ]
        )
    ]

    posture = resolve_posture(judgments)

    assert posture.posture == "capacity-constrained"


def test_posture_prefers_risky_over_degraded():
    judgments = [
        Judgment(
            state="degraded",
            confidence=0.99,
            impact_scope="local",
            urgency="observe",
            recommended_posture="continue",
            evidence=[
                Evidence(
                    source="cpu",
                    observation="CPU elevated",
                    baseline="40%",
                    deviation="+15%"
                )
            ]
        ),
        Judgment(
            state="risky",
            confidence=0.70,
            impact_scope="system-wide",
            urgency="act-now",
            recommended_posture="stop",
            evidence=[
                Evidence(
                    source="system",
                    observation="Unsafe operating condition detected",
                    baseline="normal",
                    deviation="risky state"
                )
            ]
        )
    ]

    posture = resolve_posture(judgments)

    assert posture.posture == "recovery-required"


def test_posture_supports_dictionary_judgments():
    posture = resolve_posture([
        {"state": "constrained", "confidence": 0.8}
    ])

    assert posture.posture == "capacity-constrained"
    assert posture.reasoning == (
        "Derived from constrained condition with confidence 0.80. "
        "Active conditions: constrained (0.80)"
    )
