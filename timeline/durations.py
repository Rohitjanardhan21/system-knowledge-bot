import json
from pathlib import Path
from datetime import datetime, timezone

HISTORY_DIR = Path("system_state/history")


def _parse_ts(ts: str) -> datetime:
    """
    Parse ISO timestamp and normalize to UTC-aware datetime.
    """
    dt = datetime.fromisoformat(ts.replace("Z", ""))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_posture_durations(date_str: str):
    """
    Computes posture durations for a given date (YYYY-MM-DD).

    Returns:
    {
        "total_seconds": int,
        "segments": [
            {"posture": "idle-capable", "seconds": 3600},
            ...
        ]
    }
    """

    files = sorted(HISTORY_DIR.glob(f"{date_str}*.json"))
    if not files:
        return {"total_seconds": 0, "segments": []}

    records = []

    for f in files:
        try:
            if f.stat().st_size == 0:
                continue

            with open(f) as fh:
                r = json.load(fh)

            ts = _parse_ts(r["timestamp"])
            posture = r["posture"]["posture"]

            records.append((ts, posture))

        except (json.JSONDecodeError, KeyError, ValueError):
            continue

    if not records:
        return {"total_seconds": 0, "segments": []}

    records.sort(key=lambda x: x[0])

    segments = []

    for i, (ts, posture) in enumerate(records):
        if i + 1 < len(records):
            next_ts = records[i + 1][0]
        else:
            next_ts = datetime.now(timezone.utc)

        seconds = max(0, int((next_ts - ts).total_seconds()))
        if seconds > 0:
            segments.append({
                "posture": posture,
                "seconds": seconds
            })

    total = sum(s["seconds"] for s in segments)

    return {
        "total_seconds": total,
        "segments": segments
    }
