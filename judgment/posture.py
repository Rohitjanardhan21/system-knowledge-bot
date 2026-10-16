from judgment.models import Judgment, SystemPostureResult


def resolve_posture(judgments: list[Judgment]) -> SystemPostureResult:
    if not judgments:
        return SystemPostureResult(
            posture="idle-capable",
            reasoning="No significant deviations from baseline."
        )

    priority = {
        "risky": 3,
        "constrained": 2,
        "degraded": 1,
        "stable": 0,
    }

    def get_value(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    worst = max(
        judgments,
        key=lambda j: (
            priority.get(get_value(j, "state", "UNKNOWN"), -1),
            get_value(j, "confidence", 0.0),
        ),
    )

    state = get_value(worst, "state", "UNKNOWN")
    confidence = float(get_value(worst, "confidence", 0.0))

    if state == "stable":
        posture = "work-stable"
    elif state == "degraded":
        posture = "performance-sensitive"
    elif state == "constrained":
        posture = "capacity-constrained"
    else:
        posture = "recovery-required"

    active_conditions = []

    for judgment in judgments:
        j_state = get_value(judgment, "state", "UNKNOWN")
        j_confidence = float(
            get_value(judgment, "confidence", 0.0)
        )

        evidence = get_value(judgment, "evidence", [])

        if evidence:
            primary = evidence[0]

            source = get_value(
                primary,
                "source",
                "unknown",
            )

            observation = get_value(
                primary,
                "observation",
                "No detailed observation available.",
            )

            active_conditions.append(
                f"{j_state} ({j_confidence:.2f}): "
                f"{source} — {observation}"
            )

        else:
            active_conditions.append(
                f"{j_state} ({j_confidence:.2f})"
            )

    reasoning = (
        f"Derived from {state} condition with confidence "
        f"{confidence:.2f}. "
        f"Active conditions: "
        f"{'; '.join(active_conditions)}"
    )

    return SystemPostureResult(
        posture=posture,
        reasoning=reasoning,
    )
