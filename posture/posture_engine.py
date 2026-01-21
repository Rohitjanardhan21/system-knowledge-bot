def derive_posture(facts: dict) -> dict:
    cpu = facts.get("cpu", {})
    mem = facts.get("memory", {})
    storage = facts.get("storage", {})

    # Default posture
    posture = "work-stable"
    reason = []

    # Memory pressure (most reliable)
    if mem:
        total = mem.get("total_mb", 0)
        available = mem.get("available_mb", 0)
        if total > 0:
            avail_pct = available / total
            if avail_pct < 0.15:
                posture = "capacity-constrained"
                reason.append("low memory headroom")
            elif avail_pct < 0.30:
                posture = "performance-sensitive"
                reason.append("reduced memory headroom")

    # CPU signal (weak signal, never alone)
    # (You currently don’t have CPU utilization, so we don’t overuse it)

    return {
        "posture": posture,
        "reasons": reason
    }
