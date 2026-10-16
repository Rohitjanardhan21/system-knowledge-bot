import json
import time
from pathlib import Path
from datetime import datetime, timezone

from system_collectors.factory import get_collector


HISTORY_DIR = Path("system_facts/history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

MAX_SNAPSHOTS = 1440  # ~24 hours at 1 snapshot/minute


def save_snapshot():
    collector = get_collector()
    facts = collector.collect_all()

    now = datetime.now(timezone.utc)
    facts["_snapshot"] = {
        "timestamp": now.isoformat(),
        "epoch": time.time()
    }

    filename = now.strftime("%Y%m%d_%H%M%S_%f") + ".json"
    path = HISTORY_DIR / filename

    with path.open("w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2)

    # Keep the newest MAX_SNAPSHOTS only
    snapshots = sorted(
        HISTORY_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for old in snapshots[MAX_SNAPSHOTS:]:
        try:
            old.unlink()
        except OSError:
            pass

    return path


if __name__ == "__main__":
    path = save_snapshot()
    print(f"Snapshot saved: {path}")
