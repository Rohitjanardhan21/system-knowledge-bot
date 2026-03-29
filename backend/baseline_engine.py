# backend/baseline_engine.py

import statistics
import json
import os
from backend.history_engine import load_recent_history

WINDOW = 30
BASELINE_PATH = "system_facts/baseline.json"

os.makedirs("system_facts", exist_ok=True)


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
# CORE BASELINE ANALYSIS
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

    # Z-score
    z = (latest - mean) / std if std > 0 else 0

    if z > 2:
        status = "high_anomaly"
    elif z > 1:
        status = "moderate_anomaly"
    elif z < -2:
        status = "low_anomaly"
    else:
        status = "normal"

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


# =========================================================
# 🔥 REQUIRED SYSTEM FUNCTIONS (FIX IMPORT ERROR)
# =========================================================

_baseline_store = []


def update(cpu_value: float):
    """Store latest CPU values for quick baseline tracking"""
    _baseline_store.append(cpu_value)

    if len(_baseline_store) > WINDOW:
        _baseline_store.pop(0)

    try:
        with open(BASELINE_PATH, "w") as f:
            json.dump(_baseline_store, f)
    except Exception:
        pass


def get_baseline():
    """Return average CPU baseline"""
    if not _baseline_store:
        try:
            if os.path.exists(BASELINE_PATH):
                with open(BASELINE_PATH, "r") as f:
                    data = json.load(f)
                    return sum(data) / len(data) if data else 50
        except Exception:
            return 50

    return sum(_baseline_store) / len(_baseline_store)
