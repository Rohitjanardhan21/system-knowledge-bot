def explain_cpu(facts: dict, posture: str) -> str:
    cpu = facts.get("cpu")

    if not cpu:
        return "I don’t have visibility into CPU metrics on this system."

    usage = cpu["usage_percent"]
    cores = cpu["cores"]

    lines = []

    # 1. How CPU works (static, safe)
    lines.append(
        "The CPU executes tasks by scheduling work across available cores. "
        "High usage means most cores are busy, not necessarily that the system is unhealthy."
    )

    # 2. What is happening now (facts)
    lines.append("")
    lines.append("Current observation:")
    lines.append(f"- CPU usage: {usage:.1f}% across {cores} cores")

    # 3. What it means (posture-aware, conservative)
    lines.append("")
    lines.append("Operational interpretation:")

    if posture in ("idle-capable", "work-stable"):
        lines.append(
            "CPU usage is within normal operating range for this system. "
            "No performance risk is indicated."
        )
    elif posture == "performance-sensitive":
        lines.append(
            "CPU is under moderate pressure. The system remains stable, "
            "but additional parallel work may increase latency."
        )
    else:
        lines.append(
            "CPU pressure is high relative to normal behavior. "
            "The system may have limited headroom for new workload."
        )

    return "\n".join(lines)
