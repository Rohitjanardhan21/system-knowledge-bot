def detect_intent(question: str) -> str:
    q = question.lower().strip()

    # -------------------------
    # Explicit baseline checks
    # -------------------------
    if "memory" in q and "normal" in q:
        return "SYSTEM_BASELINE"
    if "disk" in q and "normal" in q:
        return "SYSTEM_BASELINE"
    if "unusual" in q or "usual" in q or "anomaly" in q:
        return "SYSTEM_BASELINE"

    # -------------------------
    # Trend / temporal
    # -------------------------
    if "trend" in q or "getting worse" in q or "getting better" in q:
        return "SYSTEM_TREND"

    # -------------------------
    # Priority / severity
    # -------------------------
    if "important" in q or "priority" in q or "matters most" in q:
        return "SYSTEM_PRIORITY"

    # -------------------------
    # Impact / tradeoffs
    # -------------------------
    if "impact" in q or "tradeoff" in q or "help" in q or "improve" in q:
        return "SYSTEM_IMPACT"

    # -------------------------
    # Capability
    # -------------------------
    if (
        "can this system" in q
        or "handle" in q
        or "suitable" in q
        or "good for" in q
    ):
        return "SYSTEM_CAPABILITY"

    # -------------------------
    # Hardware degradation
    # -------------------------
    if "degrad" in q or "hardware" in q or "failing" in q:
        return "DEGRADATION_CHECK"

    # -------------------------
    # System health
    # -------------------------
    if "healthy" in q or "system health" in q or "status" in q:
        return "SYSTEM_STATUS"

    # -------------------------
    # Slowness
    # -------------------------
    if "slow" in q or "lag" in q or "performance" in q:
        return "SYSTEM_SLOW"

    # -------------------------
    # Watch / monitor
    # -------------------------
    if "watch" in q or "monitor" in q:
        return "ENABLE_WATCH"

    # -------------------------
    # Raw facts
    # -------------------------
    if "cpu" in q:
        return "CPU_INFO"
    if "ram" in q or "memory" in q:
        return "MEMORY_STATUS"
    if "disk" in q or "storage" in q:
        return "STORAGE_STATUS"

    return "UNKNOWN"
