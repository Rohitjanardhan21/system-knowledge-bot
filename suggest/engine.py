from suggest.model import Suggestion

def generate_suggestions(posture: str, bottleneck: str | None) -> list[Suggestion]:
    suggestions = []

    if posture in ("idle-capable", "work-stable"):
        # Silence is correct here
        return []

    if posture == "performance-sensitive":
        suggestions.append(
            Suggestion(
                message=(
                    "The system is operating under moderate pressure. "
                    "If responsiveness matters, you may want to avoid adding new parallel workload."
                ),
                confidence=0.6,
                tone="neutral"
            )
        )

    if posture == "capacity-constrained":
        suggestions.append(
            Suggestion(
                message=(
                    "System headroom is limited relative to normal behavior. "
                    "Deferring non-essential work may help maintain stability."
                ),
                confidence=0.75,
                tone="cautious"
            )
        )

    if bottleneck:
        suggestions.append(
            Suggestion(
                message=(
                    f"The current limiting resource appears to be {bottleneck.upper()}. "
                    "Any additional load affecting this resource may have outsized impact."
                ),
                confidence=0.5,
                tone="neutral"
            )
        )

    return suggestions
