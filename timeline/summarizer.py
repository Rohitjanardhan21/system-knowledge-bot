def summarize_timeline(timeline):
    if not timeline:
        return "No posture changes observed."

    lines = ["System posture changes:\n"]

    for entry in timeline:
        lines.append(
            f"- {entry['timestamp']}: entered {entry['posture']}"
        )

    return "\n".join(lines)
