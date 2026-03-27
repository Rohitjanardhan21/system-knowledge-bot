import statistics
from backend.history_engine import load_recent_history

WINDOW = 30


# ---------------------------------------------------------
# SAFE METRIC EXTRACTOR
# ---------------------------------------------------------
def extract_metric(snap, metric):
    try:
        metrics = snap.get("metrics", {})

        if metric in metrics:
            return metrics.get(metric)

        mapping = {
            "cpu_pct": "cpu",
            "mem_pct": "memory",
            "disk_pct": "disk"
        }

        mapped = mapping.get(metric)
        if mapped:
            return metrics.get(mapped)

    except Exception:
        return None

    return None


# ---------------------------------------------------------
# CORE BASELINE
# ---------------------------------------------------------
def compute_baseline(metric: str, window: int = WINDOW):

    history = load_recent_history(window)
    values = []

    for snap in history:
        v = extract_metric(snap, metric)

        if isinstance(v, (int, float)):
            values.append(v)

    if len(values) < 5:
        return None

    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0

    latest = values[-1]

    # -----------------------------------------------------
    # 🔥 Z-SCORE (ANOMALY)
    # -----------------------------------------------------
    if std > 0:
        z = (latest - mean) / std
    else:
        z = 0

    # -----------------------------------------------------
    # 🔥 CLASSIFICATION
    # -----------------------------------------------------
    if z > 2:
        status = "high_anomaly"
    elif z > 1:
        status = "moderate_anomaly"
    elif z < -2:
        status = "low_anomaly"
    else:
        status = "normal"

    # -----------------------------------------------------
    # 🔥 CONFIDENCE
    # -----------------------------------------------------
    confidence = min(1.0, len(values) / window)

    return {
        "mean": round(mean, 2),
        "std": round(std, 2),
        "min": min(values),
        "max": max(values),
        "latest": latest,
        "z_score": round(z, 2),
        "status": status,
        "confidence": round(confidence, 2)
    }


# ---------------------------------------------------------
# DISK GROWTH
# ---------------------------------------------------------
def compute_disk_growth(window: int = WINDOW):

    history = load_recent_history(window)
    values = []

    for snap in history:
        v = extract_metric(snap, "disk")

        if isinstance(v, (int, float)):
            values.append(v)

    if len(values) < 6:
        return None

    start = values[0]
    end = values[-1]

    delta = end - start

    # -----------------------------------------------------
    # 🔥 TREND CLASSIFICATION
    # -----------------------------------------------------
    if delta > 5:
        trend = "rapid_growth"
    elif delta > 2:
        trend = "steady_growth"
    else:
        trend = "stable"

    return {
        "start": start,
        "end": end,
        "delta": round(delta, 2),
        "rate": round(delta / len(values), 3),
        "trend": trend
    }
