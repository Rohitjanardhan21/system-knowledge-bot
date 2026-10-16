from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone


STATE_PATH = Path(r".\state\latest.json")


def _load_state():
    if not STATE_PATH.exists():
        return None

    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            state = json.load(f)

        return state if isinstance(state, dict) else None

    except (json.JSONDecodeError, OSError):
        return None


def _save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def get_pending_confirmations():
    state = _load_state()

    if not state:
        return []

    pending = []

    for action in state.get("actions", []):
        if not isinstance(action, dict):
            continue

        if action.get("status") == "requires-confirmation":
            pending.append(action)

    return pending


def approve_action(action_name):
    state = _load_state()

    if not state:
        return {
            "status": "rejected",
            "reason": "State file is unavailable.",
        }

    actions = state.get("actions", [])

    for action in actions:
        if not isinstance(action, dict):
            continue

        if action.get("action") != action_name:
            continue

        if action.get("status") != "requires-confirmation":
            return {
                "status": "rejected",
                "action": action_name,
                "reason": "Action is not awaiting confirmation.",
            }

        action["status"] = "approved"
        action["confirmation"] = {
            "decision": "approved",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        _save_state(state)

        return {
            "status": "approved",
            "action": action_name,
            "reason": "Action explicitly approved.",
        }

    return {
        "status": "rejected",
        "action": action_name,
        "reason": "Action not found.",
    }


def reject_action(action_name):
    state = _load_state()

    if not state:
        return {
            "status": "rejected",
            "reason": "State file is unavailable.",
        }

    actions = state.get("actions", [])

    for action in actions:
        if not isinstance(action, dict):
            continue

        if action.get("action") != action_name:
            continue

        if action.get("status") != "requires-confirmation":
            return {
                "status": "rejected",
                "action": action_name,
                "reason": "Action is not awaiting confirmation.",
            }

        action["status"] = "rejected"
        action["confirmation"] = {
            "decision": "rejected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        _save_state(state)

        return {
            "status": "rejected",
            "action": action_name,
            "reason": "Action explicitly rejected.",
        }

    return {
        "status": "rejected",
        "action": action_name,
        "reason": "Action not found.",
    }
