import os
import json

HISTORY_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "system_state",
    "history"
)

def extract_posture_timeline(day: str | None = None):
    """
    Returns List[Tuple[timestamp: str, posture: str]]
    """
    if not os.path.isdir(HISTORY_DIR):
        return []

    events = []

    for fname in sorted(os.listdir(HISTORY_DIR)):
        if not fname.endswith(".json"):
            continue

        path = os.path.join(HISTORY_DIR, fname)

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue

        ts = data.get("timestamp")
        posture_obj = data.get("posture")

        if not ts or not posture_obj:
            continue

        # 🔑 NORMALIZATION HERE
        if isinstance(posture_obj, dict):
            posture = posture_obj.get("posture")
        else:
            posture = posture_obj

        if not posture:
            continue

        if day and not ts.startswith(day):
            continue

        events.append((ts, posture))

    return events
