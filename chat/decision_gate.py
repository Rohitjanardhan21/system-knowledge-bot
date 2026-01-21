def should_speak(
    severity_levels,
    observations,
    intent,
    freshness_ok=True
):
    """
    Determines whether the system should surface information proactively.
    """

    # Always speak if data freshness is violated
    if not freshness_ok:
        return True

    # Always speak if user explicitly asked
    explicit_intents = {
        "SYSTEM_STATUS",
        "SYSTEM_TREND",
        "SYSTEM_BASELINE",
        "SYSTEM_PRIORITY",
        "SYSTEM_IMPACT",
        "SYSTEM_CAPABILITY",
        "DEGRADATION_CHECK"
    }

    if intent in explicit_intents:
        return True

    # Speak only if something meaningful exists
    if any(s in ("warning", "attention") for s in severity_levels):
        return True

    if observations:
        return True

    return False
