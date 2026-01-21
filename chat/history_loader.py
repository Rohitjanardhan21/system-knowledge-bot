import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
HISTORY_DIR = os.path.join(BASE_DIR, "system_facts", "history")

def load_recent_history(limit=5):
    if not os.path.exists(HISTORY_DIR):
        return []

    files = sorted(os.listdir(HISTORY_DIR))[-limit:]
    snapshots = []

    for f in files:
        path = os.path.join(HISTORY_DIR, f)
        with open(path) as file:
            snapshots.append(json.load(file))

    return snapshots
