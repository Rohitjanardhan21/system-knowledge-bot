
from __future__ import annotations

import json
from pathlib import Path

from judgment.lifecycle import begin_execution, complete_execution


STATE_PATH = Path("state") / "latest.json"


def _load_state():
    if not STATE_PATH.exists():
        return {"actions": []}

    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"actions": []}


def _find_action(state, action_name):
    action_name = str(action_name)

    for item in state.get("actions", []):
        if isinstance(item, dict) and item.get("action") == action_name:
            return item

    return {"action": action_name, "status": "approved"}


def build_execution_plan(validated_actions):
    plan = []

    for action in validated_actions:
        status = action.get("status", "blocked")

        if status == "approved":
            execution_mode = "automatic"

        elif status == "requires-confirmation":
            execution_mode = "confirmation-required"

        else:
            execution_mode = "blocked"

        plan.append({
            "action": action.get("action", "unknown"),
            "priority": action.get("priority", "unknown"),
            "status": status,
            "execution_mode": execution_mode,
            "reason": action.get(
                "reason",
                "No reason provided."
            ),
            "validation_reason": action.get(
                "validation_reason",
                "No validation reason provided."
            ),
        })

    return plan


def execute_action(action_name, result=None, complete=False, success=True):
    action = _find_action(_load_state(), action_name)

    if complete:
        if action.get("status") != "executing":
            start_result = begin_execution(action)
            if start_result.get("status") != "executing":
                return start_result

        return complete_execution(
            action,
            success=success,
            result=result,
        )

    return begin_execution(action)


if __name__ == "__main__":
    print("Execution planner loaded successfully.")
