from pathlib import Path
import json

STATE_PATH = Path("state/latest.json")
AUDIT_PATH = Path("state/audit.json")


def _load_json(path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            value = json.load(f)

        return value

    except (json.JSONDecodeError, OSError):
        return default


def load_latest_state():
    return _load_json(STATE_PATH, {})


def load_audit():
    return _load_json(AUDIT_PATH, [])


def get_action_state(action_name):
    state = load_latest_state()

    for action in state.get("actions", []):
        if action.get("action") == action_name:
            return action

    return None
