from pathlib import Path
import json
from dataclasses import asdict, is_dataclass

STATE_PATH = Path("state/latest.json")
HISTORY_PATH = Path("state/history.json")

MAX_HISTORY = 20


def _serialize(value):
    if is_dataclass(value):
        return asdict(value)

    if isinstance(value, dict):
        return value

    if isinstance(value, list):
        return [_serialize(item) for item in value]

    if hasattr(value, "__dict__"):
        return value.__dict__

    return value


def _load_history():
    if not HISTORY_PATH.exists():
        return []

    try:
        with HISTORY_PATH.open("r", encoding="utf-8") as f:
            history = json.load(f)

        if isinstance(history, list):
            return history

    except (json.JSONDecodeError, OSError):
        pass

    return []


def write_state(
    facts,
    judgments,
    posture,
    actions=None,
    execution_plan=None,
    execution_results=None,
):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    serialized_facts = _serialize(facts)
    serialized_judgments = [_serialize(j) for j in judgments]
    serialized_posture = _serialize(posture)

    state = {
        "facts": serialized_facts,
        "judgments": serialized_judgments,
        "posture": serialized_posture,
        "actions": _serialize(actions or []),
        "execution_plan": _serialize(execution_plan or []),
        "execution_results": _serialize(execution_results or []),
    }

    # Current state
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)

    # Historical telemetry
    history = _load_history()

    history.append({
        "timestamp": serialized_facts.get("timestamp"),
        "cpu": serialized_facts.get("cpu", {}),
        "memory": serialized_facts.get("memory", {}),
        "disk": serialized_facts.get("disk", {}),
    })

    history = history[-MAX_HISTORY:]

    with HISTORY_PATH.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, default=str)

    return STATE_PATH
