from judgment.models import Judgment, Evidence

def cpu_rule(cpu_now: float, cpu_baseline: float) -> Judgment | None:
    deviation = cpu_now - cpu_baseline

    if deviation < 10:
        return None

    state = "degraded" if deviation < 25 else "constrained"
    urgency = "observe" if deviation < 20 else "act-soon"

    return Judgment(
        state=state,
        confidence=0.7,
        impact_scope="local",
        urgency=urgency,
        recommended_posture="continue",
        evidence=[
            Evidence(
                source="cpu",
                observation=f"CPU usage at {cpu_now:.1f}%",
                baseline=f"{cpu_baseline:.1f}%",
                deviation=f"+{deviation:.1f}%"
            )
        ]
    )
