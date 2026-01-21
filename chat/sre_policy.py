def enforce_sre_policy(facts, health_summary):
    """
    Applies SRE rules on top of health evaluation.
    Returns (final_state, message_override)
    """

    metadata = facts.get("metadata", {})
    ttl = metadata.get("ttl_seconds", 0)

    # ---------- Rule 1: Freshness is mandatory ----------
    collected_at = metadata.get("collected_at")
    if not collected_at:
        return (
            "degraded",
            "System health cannot be trusted because freshness information is missing."
        )

    from datetime import datetime, timezone
    collected_time = datetime.fromisoformat(collected_at).replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - collected_time).total_seconds()

    if age > ttl:
        return (
            "degraded",
            "System data is stale, so the current health assessment may not be reliable."
        )

    # ---------- Rule 2: Critical components missing ----------
    if "cpu" not in facts or "memory" not in facts:
        return (
            "degraded",
            "Critical system information is missing, so health status is degraded."
        )

    # ---------- Rule 3: Disk health missing is WARNING, not failure ----------
    disk_health = facts.get("disk_health", {})
    if disk_health.get("status") == "unknown":
        return (
            "warning",
            "Disk health could not be evaluated, but this does not indicate an immediate failure."
        )

    # ---------- Rule 4: Battery N/A is informational ----------
    # (no override needed)

    return ("healthy", None)
