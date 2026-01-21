from judgment.models import Judgment, SystemPostureResult

def resolve_posture(judgments: list[Judgment]) -> SystemPostureResult:
    if not judgments:
        return SystemPostureResult(
            posture="idle-capable",
            reasoning="No significant deviations from baseline."
        )

    worst = max(judgments, key=lambda j: j.confidence)

    if worst.state == "stable":
        posture = "work-stable"
    elif worst.state == "degraded":
        posture = "performance-sensitive"
    elif worst.state == "constrained":
        posture = "capacity-constrained"
    else:
        posture = "recovery-required"

    return SystemPostureResult(
        posture=posture,
        reasoning=f"Derived from {worst.state} condition with confidence {worst.confidence:.2f}"
    )
