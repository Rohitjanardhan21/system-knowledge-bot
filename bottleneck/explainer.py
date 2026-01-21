from bottleneck.model import BottleneckResult

def explain_bottleneck(result: dict) -> str:
    primary = result["primary"]
    secondary = result["secondary"]
    confidence = result["confidence"]
    evidence = result["evidence"]

    if primary == "unknown":
        return (
            "I cannot confidently identify a system bottleneck at this time.\n"
            "Available evidence is insufficient."
        )

    lines = []
    lines.append(f"Primary bottleneck: {primary.upper()}")
    lines.append(f"Confidence: {confidence:.2f}")
    lines.append("")

    lines.append("Evidence:")
    for e in evidence:
        lines.append(f"- {e}")

    if secondary:
        lines.append("")
        lines.append("Secondary contributors:")
        for s in secondary:
            lines.append(f"- {s.upper()}")

    lines.append("")
    lines.append(
        "This identifies the current limiting resource only. "
        "It does not imply a fault or recommend corrective action."
    )

    return "\n".join(lines)
