import json
from datetime import datetime, timezone
from pathlib import Path

from posture.posture_engine import derive_posture

HISTORY_DIR = Path("system_state/history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def write_posture_history(facts: dict):
    posture = derive_posture(facts)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "posture": posture,
    }

    fname = record["timestamp"].replace(":", "-") + ".json"
    path = HISTORY_DIR / fname

    with open(path, "w") as f:
        json.dump(record, f, indent=2)
