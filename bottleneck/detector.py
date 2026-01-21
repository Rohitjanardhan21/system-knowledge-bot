def detect_bottleneck(facts: dict, posture: str) -> dict:
    pressures = {}

    # CPU pressure
    cpu = facts.get("cpu")
    if cpu:
        pressures["cpu"] = cpu["usage_percent"]

    # Memory pressure
    mem = facts.get("memory")
    if mem:
        pressures["memory"] = (mem["used_mb"] / mem["total_mb"]) * 100

    # Disk pressure (if available)
    disk = facts.get("disk")
    if disk:
        pressures["disk"] = disk.get("used_percent", 0)

    # Thermal pressure
    temp = facts.get("temperature")
    if temp:
        pressures["thermal"] = temp

    if not pressures:
        return {
            "primary": "unknown",
            "secondary": [],
            "confidence": 0.0,
            "evidence": ["No resource pressure data available"]
        }

    # Rank pressures relative to posture
    ranked = sorted(pressures.items(), key=lambda x: x[1], reverse=True)

    primary, primary_value = ranked[0]
    secondary = [r[0] for r in ranked[1:] if r[1] > 0]

    confidence = 0.3
    evidence = []

    if posture == "performance-sensitive":
        confidence = 0.6
    elif posture == "capacity-constrained":
        confidence = 0.8

    evidence.append(f"{primary.upper()} shows highest relative pressure")

    return {
        "primary": primary,
        "secondary": secondary,
        "confidence": confidence,
        "evidence": evidence
    }
