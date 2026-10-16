from __future__ import annotations


def check_preconditions(action, current_facts):
    action_name = action.get("action")

    memory = current_facts.get("memory", {})
    disk = current_facts.get("disk", {})

    if action_name == "reduce-memory-pressure":
        utilization = memory.get("utilization", 0)

        if utilization >= 85:
            return {
                "allowed": True,
                "action": action_name,
                "reason": (
                    f"Memory utilization remains high at {utilization}%."
                ),
            }

        return {
            "allowed": False,
            "action": action_name,
            "reason": (
                f"Memory utilization is now {utilization}%; "
                "precondition no longer holds."
            ),
        }

    if action_name == "free-disk-space":
        utilization = disk.get("utilization", 0)

        if utilization >= 85:
            return {
                "allowed": True,
                "action": action_name,
                "reason": (
                    f"Disk utilization remains high at {utilization}%."
                ),
            }

        return {
            "allowed": False,
            "action": action_name,
            "reason": (
                f"Disk utilization is now {utilization}%; "
                "precondition no longer holds."
            ),
        }

    if action_name == "avoid-heavy-workloads":
        utilization = disk.get("utilization", 0)

        if utilization >= 85:
            return {
                "allowed": True,
                "action": action_name,
                "reason": (
                    f"System remains capacity-constrained; "
                    f"disk utilization is {utilization}%."
                ),
            }

        return {
            "allowed": False,
            "action": action_name,
            "reason": "System is no longer capacity-constrained.",
        }

    return {
        "allowed": False,
        "action": action_name,
        "reason": "Unknown action; precondition cannot be verified.",
    }
