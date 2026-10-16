from preflight.models import PreflightResult

def evaluate_preflight(posture: str, judgments: list) -> PreflightResult:
    states = {getattr(j, "state", None) for j in judgments}

    if "risky" in states:
        return PreflightResult(
            decision="defer",
            confidence=0.75,
            posture=posture,
            reasoning="A risky judgment requires deferring new workload."
        )

    if "constrained" in states:
        return PreflightResult(
            decision="defer",
            confidence=0.75,
            posture=posture,
            reasoning="A constrained judgment requires deferring new workload."
        )

    if posture in ("idle-capable", "work-stable"):
        return PreflightResult(
            decision="safe",
            confidence=0.85,
            posture=posture,
            reasoning="System is operating within normal capacity."
        )

    if posture == "performance-sensitive":
        return PreflightResult(
            decision="risky",
            confidence=0.65,
            posture=posture,
            reasoning="System is under moderate pressure. Additional workload may impact responsiveness."
        )

    return PreflightResult(
        decision="defer",
        confidence=0.75,
        posture=posture,
        reasoning="System is currently constrained. Deferring new workload is advised."
    )
