from pathlib import Path
import json
from datetime import datetime

HISTORY = Path("system_facts/history")


def parse_ts(filename):

    stem = filename.replace(".json", "")

    try:
        return datetime.fromisoformat(stem)
    except Exception:
        # convert 2026-01-18T12-14-59 → iso
        parts = stem.split("T")
        if len(parts) == 2:
            date = parts[0]
            time = parts[1].replace("-", ":")
            fixed = f"{date}T{time}"
            return datetime.fromisoformat(fixed)

        raise


def load_recent(limit=30):

    if not HISTORY.exists():
        return []

    rows = []

    for p in sorted(HISTORY.glob("*.json"))[-limit:]:
        try:
            ts = parse_ts(p.name)
            rows.append(json.loads(p.read_text()))
        except Exception:
            continue

    return rows


def compute_trends():

    rows = load_recent()

    if len(rows) < 5:
        return {}

    cpu_vals = []
    mem_vals = []
    disk_vals = []

    for r in rows:
        m = r.get("metrics", {})

        cpu_vals.append(
            m.get("cpu", {}).get("usage_percent", 0)
        )

        mem_vals.append(
            m.get("memory", {}).get("percent", 0)
        )

        disks = m.get("disk", [])
        root = next((d for d in disks if d.get("mount") == "/"), None)
        if root:
            disk_vals.append(root.get("percent", 0))

    def slope(arr):
        if len(arr) < 2:
            return 0
        return round(arr[-1] - arr[0], 2)

    return {
        "cpu_slope": slope(cpu_vals),
        "memory_slope": slope(mem_vals),
        "disk_slope": slope(disk_vals),
    }
