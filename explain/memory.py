def explain_memory(facts: dict, posture: str) -> str:
    mem = facts.get("memory")

    if not mem:
        return "I don’t have visibility into memory metrics on this system."

    used = mem["used_mb"]
    total = mem["total_mb"]
    percent = (used / total) * 100

    lines = []

    lines.append(
        "Memory is used to keep active data readily accessible. "
        "High memory usage is common and not inherently problematic unless it causes pressure."
    )

    lines.append("")
    lines.append("Current observation:")
    lines.append(f"- Memory usage: {used:.0f} MB of {total:.0f} MB ({percent:.1f}%)")

    lines.append("")
    lines.append("Operational interpretation:")

    if posture in ("idle-capable", "work-stable"):
        lines.append(
            "Memory usage appears normal. There is no indication of memory pressure."
        )
    elif posture == "performance-sensitive":
        lines.append(
            "Memory usage is elevated. The system may rely more on cache eviction "
            "or background reclamation."
        )
    else:
        lines.append(
            "Memory pressure is high relative to baseline. "
            "This may limit performance under additional load."
        )

    return "\n".join(lines)
