
from __future__ import annotations


DESTRUCTIVE_ACTIONS = {
    "free-disk-space",
}


def validate_actions(actions, posture):
    posture_name = getattr(
        posture,
        "posture",
        "idle-capable",
    )

    validated = []

    for action in actions:
        name = action.get("action", "unknown")

        if name in DESTRUCTIVE_ACTIONS:
            status = "requires-confirmation"
            reason = (
                "Action may modify or remove system data "
                "and therefore requires explicit confirmation."
            )

        else:
            status = "approved"
            reason = (
                "Action is non-destructive and may proceed "
                "within the current system posture."
            )

        validated.append({
            **action,
            "status": status,
            "validation_reason": reason,
            "posture_at_validation": posture_name,
        })

    return validated


if __name__ == "__main__":
    print("Action safety validator loaded successfully.")
