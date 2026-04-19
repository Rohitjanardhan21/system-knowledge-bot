"""
History Engine

Responsible for:

- writing periodic snapshots (already implemented elsewhere)
- loading recent history windows
- loading yesterday's snapshot
- supporting trend / baseline engines

Phase-5 compatible interface.
"""

from pathlib import Path
import json
from datetime import datetime, timedelta

HISTORY_DIR = Path("system_facts/history")


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _load_snapshot(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


# ---------------------------------------------------------
# Load recent history window
# ---------------------------------------------------------

def load_recent_history(limit: int = 30):
    """
    Returns the most recent N flattened snapshots.
    """

    if not HISTORY_DIR.exists():
        return []

    files = sorted(HISTORY_DIR.glob("*.json"))[-200:]

    snapshots = []
    for f in files:
        snap = _load_snapshot(f)
        if snap:
            snapshots.append(snap)

    return snapshots


# ---------------------------------------------------------
# Yesterday snapshot
# ---------------------------------------------------------

def load_yesterday_snapshot():
    """
    Returns the latest snapshot from the previous day.
    """

    if not HISTORY_DIR.exists():
        return None

    yesterday = datetime.utcnow().date() - timedelta(days=1)

    candidates = []

    for f in HISTORY_DIR.glob("*.json"):
        try:
            ts = datetime.fromisoformat(f.stem)
        except Exception:
            continue

        if ts.date() == yesterday:
            snap = _load_snapshot(f)
            if snap:
                candidates.append((ts, snap))

    if not candidates:
        return None

    # Return most recent snapshot from yesterday
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]
# ---------------------------------------------------------
# Full history (for temporal + advanced reasoning)
# ---------------------------------------------------------

def load_history():
    """
    Returns ALL available history snapshots in chronological order.
    Used for temporal + causal reasoning engines.
    """

    if not HISTORY_DIR.exists():
        return []

    files = sorted(HISTORY_DIR.glob("*.json"))

    snapshots = []
    for f in files:
        snap = _load_snapshot(f)
        if snap:
            snapshots.append(snap)

    return snapshots
