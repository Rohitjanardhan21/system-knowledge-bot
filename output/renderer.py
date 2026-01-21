from judgment.models import Judgment, SystemPostureResult

def render(judgment: Judgment, posture: SystemPostureResult) -> str:
    lines = []

    lines.append(f"System posture: {posture.posture}")
    lines.append(posture.reasoning)
    lines.append("")

    for e in judgment.evidence:
        lines.append(f"- {e.source}: {e.observation}")
        if e.baseline:
            lines.append(f"  baseline: {e.baseline} ({e.deviation})")

    lines.append("")
    lines.append(f"Recommended posture: {judgment.recommended_posture}")

    return "\n".join(lines)
