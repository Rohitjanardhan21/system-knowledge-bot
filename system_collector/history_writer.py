import json
from pathlib import Path
from datetime import datetime, timezone

HISTORY_DIR = Path("system_facts/history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def write_snapshot(snapshot: dict):

    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    path = HISTORY_DIR / f"{ts}.json"

    path.write_text(json.dumps(snapshot, indent=2))

    return path
