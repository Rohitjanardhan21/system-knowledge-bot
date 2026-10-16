
from __future__ import annotations


def recommend_actions(judgments, posture):
    actions = []

    posture_name = getattr(posture, "posture", "idle-capable")

    for judgment in judgments:
        state = getattr(judgment, "state", "")
        source = "unknown"

        evidence = getattr(judgment, "evidence", [])
        if evidence:
            source = getattr(evidence[0], "source", "unknown")

        if source == "system.memory":
            if state == "risky":
                actions.append({
                    "priority": "critical",
                    "action": "reduce-memory-pressure",
                    "reason": "Memory utilization is critically high.",
                })
            elif state == "constrained":
                actions.append({
                    "priority": "high",
                    "action": "investigate-memory-usage",
                    "reason": "Memory utilization exceeds the safe threshold.",
                })

        elif source == "system.storage":
            if state == "risky":
                actions.append({
                    "priority": "critical",
                    "action": "free-disk-space",
                    "reason": "Disk utilization is critically high.",
                })
            elif state == "constrained":
                actions.append({
                    "priority": "high",
                    "action": "free-disk-space",
                    "reason": "Disk utilization exceeds the safe threshold.",
                })

        elif source == "system.cpu":
            if state == "risky":
                actions.append({
                    "priority": "critical",
                    "action": "reduce-cpu-load",
                    "reason": "CPU utilization is critically high.",
                })
            elif state == "constrained":
                actions.append({
                    "priority": "high",
                    "action": "reduce-cpu-load",
                    "reason": "CPU utilization is elevated.",
                })

        elif source == "windows.event_log":
            if state == "risky":
                actions.append({
                    "priority": "critical",
                    "action": "investigate-hardware-events",
                    "reason": "Recent critical hardware events were detected.",
                })
            elif state == "degraded":
                actions.append({
                    "priority": "high",
                    "action": "investigate-application-crashes",
                    "reason": "Recent application crashes were detected.",
                })

    if posture_name in ("recovery-required", "capacity-constrained"):
        actions.append({
            "priority": "high",
            "action": "avoid-heavy-workloads",
            "reason": f"System posture is {posture_name}.",
        })

    return actions


if __name__ == "__main__":
    print("Action engine loaded successfully.")
