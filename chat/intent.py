def detect_intent(question: str) -> str:
    q = question.lower().strip()

    # -------------------------
    # CPU
    # -------------------------
    if "cpu" in q and ("what" in q or "which" in q):
        return "CPU_INFO"

    if "what is cpu" in q or "explain cpu" in q:
        return "EXPLAIN_CPU"

    # -------------------------
    # MEMORY
    # -------------------------
    if "ram" in q and ("free" in q or "available" in q):
        return "MEMORY_STATUS"

    if "what is ram" in q or "explain ram" in q:
        return "EXPLAIN_RAM"

    # -------------------------
    # STORAGE
    # -------------------------
    if "disk" in q or "storage" in q:
        return "STORAGE_STATUS"

    # -------------------------
    # SYSTEM HEALTH
    # -------------------------
    if "health" in q or "system status" in q:
        return "SYSTEM_STATUS"

    # -------------------------
    # PERFORMANCE / SLOWNESS
    # -------------------------
    if "slow" in q or "lag" in q or "performance" in q:
        return "SYSTEM_SLOW"

    # -------------------------
    # HARDWARE DEGRADATION
    # -------------------------
    if (
        "degrad" in q
        or "failing" in q
        or "hardware problem" in q
        or "hardware issue" in q
        or "bad hardware" in q
    ):
        return "DEGRADATION_CHECK"

    # -------------------------
    # CHANGE DETECTION
    # -------------------------
    if "change" in q or "difference" in q or "recently" in q:
        return "SYSTEM_CHANGE"

    # -------------------------
    # CAPABILITY / WORKLOAD
    # -------------------------
    if (
        "workload" in q
        or "what can this system" in q
        or "what is this system good for" in q
        or "what kind of work" in q
        or "handle docker" in q
        or "handle kubernetes" in q
        or "capable of" in q
        or "good for" in q
    ):
        return "CAPABILITY_CHECK"

    # -------------------------
    # FALLBACK
    # -------------------------
    return "UNKNOWN"
