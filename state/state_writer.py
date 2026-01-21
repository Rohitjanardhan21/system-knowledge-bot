# ==========================================================
# System Knowledge Bot — State Writer
#
# Writes resolved system state to disk
# Read-only for all consumers (GUI, CLI, voice)
# ==========================================================

import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "system_state"
HISTORY_DIR = STATE_DIR / "history"

STATE_DIR.mkdir(exist_ok=True)
HISTORY_DIR.mkdir(exist_ok=True)


def write_state(facts, judgments, posture):
    timestamp = datetime.utcnow().isoformat(timespec="seconds")

    record = {
        "timestamp": timestamp,
        "facts": facts,
        "judgments": [j.__dict__ for j in judgments],
        "posture": posture.__dict__,
    }

    with open(STATE_DIR / "latest.json", "w") as f:
        json.dump(record, f, indent=2)

    with open(HISTORY_DIR / f"{timestamp}.json", "w") as f:
        json.dump(record, f, indent=2)
