def explain_slowness(reasons, confidence):
    intro = "Based on the current system state, here’s what might be affecting performance:"

    lines = [intro]

    for r in reasons:
        lines.append(f"- {r}")

    if "high" in confidence:
        closing = "These factors are very likely contributing to the slowdown."
    elif "medium" in confidence:
        closing = "These factors could be contributing to the slowdown."
    else:
        closing = "I don’t see strong system-level issues right now."

    return "\n".join(lines + [closing])
