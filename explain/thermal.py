def explain_thermal(facts: dict, posture: str) -> str:
    temp = facts.get("temperature")

    if temp is None:
        return "Thermal data is not available on this system."

    lines = []

    lines.append(
        "System temperature reflects how much heat components are generating. "
        "Short spikes are normal; sustained high temperatures can reduce headroom."
    )

    lines.append("")
    lines.append("Current observation:")
    lines.append(f"- Temperature: {temp:.1f} °C")

    lines.append("")
    lines.append("Operational interpretation:")

    if posture in ("idle-capable", "work-stable"):
        lines.append(
            "Thermal conditions are within normal operating range."
        )
    elif posture == "performance-sensitive":
        lines.append(
            "Temperature is elevated. The system may reduce boost behavior "
            "to maintain stability."
        )
    else:
        lines.append(
            "Thermal headroom is limited. Sustained workload may be constrained."
        )

    return "\n".join(lines)
