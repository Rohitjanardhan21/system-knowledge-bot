def explain_degradation(findings):
    intro = "Here’s what I can tell about potential hardware degradation:"
    lines = [intro]

    for f in findings:
        lines.append(f"- {f}")

    return "\n".join(lines)
