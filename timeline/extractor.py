import json
from pathlib import Path

HISTORY_DIR = Path("system_state/history")

def extract_posture_timeline():
    records = []

    for file in sorted(HISTORY_DIR.glob("*.json")):
        try:
            if file.stat().st_size == 0:
                # Skip empty files
                continue

            with open(file) as f:
                data = json.load(f)

            records.append(
                (data["timestamp"], data["posture"]["posture"])
            )

        except (json.JSONDecodeError, KeyError):
            # Skip corrupt or incomplete records
            continue

    timeline = []
    last_posture = None

    for timestamp, posture in records:
        if posture != last_posture:
            timeline.append({
                "timestamp": timestamp,
                "posture": posture
            })
            last_posture = posture

    return timeline
