from preflight.evaluator import evaluate_preflight


def test_idle_capable_is_safe():
    result = evaluate_preflight("idle-capable", [])
    assert result.decision == "safe"
    assert result.confidence == 0.85


def test_performance_sensitive_is_risky():
    result = evaluate_preflight("performance-sensitive", [])
    assert result.decision == "risky"
    assert result.confidence == 0.65


def test_capacity_constrained_defers():
    result = evaluate_preflight("capacity-constrained", [])
    assert result.decision == "defer"
    assert result.confidence == 0.75


def test_risky_judgment_forces_defer_even_with_safe_posture():
    from judgment.models import Judgment, Evidence

    judgments = [
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
                    deviation="risky state",
                )
            ],
        )
    ]

    result = evaluate_preflight("idle-capable", judgments)

    assert result.decision == "defer"
    assert result.posture == "idle-capable"


def test_constrained_judgment_forces_defer_even_with_safe_posture():
    from judgment.models import Judgment, Evidence

    judgments = [
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
                    deviation="+40%",
                )
            ],
        )
    ]

    result = evaluate_preflight("idle-capable", judgments)

    assert result.decision == "defer"


def test_degraded_judgment_does_not_override_safe_posture():
    from judgment.models import Judgment, Evidence

    judgments = [
        Judgment(
            state="degraded",
            confidence=0.70,
            impact_scope="local",
            urgency="observe",
            recommended_posture="continue",
            evidence=[
                Evidence(
                    source="cpu",
                    observation="CPU moderately elevated",
                    baseline="40%",
                    deviation="+15%",
                )
            ],
        )
    ]

    result = evaluate_preflight("idle-capable", judgments)

    assert result.decision == "safe"
