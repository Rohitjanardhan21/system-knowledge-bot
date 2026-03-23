import statistics
from backend.history_engine import load_recent_history

WINDOW = 30


# ---------------------------------------------------------
# Generic baseline calculator
# ---------------------------------------------------------

def compute_baseline(metric: str, window: int = WINDOW):
    history = load_recent_history(window)

    values = []

    for snap in history:
        v = snap.get(metric)
        if isinstance(v, (int, float)):
            values.append(v)

    if len(values) < 5:
        return None

    return {
        "mean": statistics.mean(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0,
        "min": min(values),
        "max": max(values),
        "latest": values[-1],
    }


# ---------------------------------------------------------
# Disk growth calculator (robust)
# ---------------------------------------------------------

def compute_disk_growth(window: int = WINDOW):
    history = load_recent_history(window)

    values = []

    for snap in history:
        v = snap.get("disk_pct")
        if isinstance(v, (int, float)):
            values.append(v)

    # Not enough clean samples
    if len(values) < 6:
        return None

    start = values[0]
    end = values[-1]

    return {
        "start": start,
        "end": end,
        "delta": round(end - start, 2),
        "rate": round((end - start) / len(values), 3),
    }
