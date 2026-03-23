import json
from pathlib import Path
from datetime import datetime

HISTORY_DIR = Path("system_facts/history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def write_snapshot(snapshot: dict):

    ts = datetime.utcnow().isoformat().replace(":", "-")
    path = HISTORY_DIR / f"{ts}.json"

    path.write_text(json.dumps(snapshot, indent=2))

    return path
