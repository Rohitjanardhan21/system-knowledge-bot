import numpy as np
from collections import deque

# -------------------------------
# CONFIG
# -------------------------------
WINDOW_SIZE = 20
SPIKE_THRESHOLD = 25
SLOPE_THRESHOLD = 1.5
OSCILLATION_THRESHOLD = 10


# -------------------------------
# TEMPORAL MEMORY (for system)
# -------------------------------
class TemporalEngine:

    def __init__(self):
        self.history = deque(maxlen=50)

    def update(self, state):
        if isinstance(state, dict):
            self.history.append({
                "cpu": float(state.get("cpu", 0)),
                "memory": float(state.get("memory", 0)),
                "disk": float(state.get("disk", 0))
            })


# -------------------------------
# UTIL FUNCTIONS
# -------------------------------
def get_recent_values(history, key):
    values = []

    for h in history[-WINDOW_SIZE:]:
        val = h.get(key)

        if isinstance(val, (int, float)):
            values.append(val)

    return values


def compute_slope(values):
    if len(values) < 2:
        return 0

    x = np.arange(len(values))
    y = np.array(values)

    try:
        slope = np.polyfit(x, y, 1)[0]
    except Exception:
        slope = 0

    return float(slope)


def detect_spike(values):
    if len(values) < 2:
        return False

    diff = values[-1] - values[-2]
    return diff > SPIKE_THRESHOLD


def detect_oscillation(values):
    if len(values) < 5:
        return False

    std_dev = np.std(values)
    return std_dev > OSCILLATION_THRESHOLD


def detect_plateau(values):
    if len(values) < 5:
        return False

    std_dev = np.std(values)
    return std_dev < 2


# -------------------------------
# MAIN ANALYSIS
# -------------------------------
def analyze_metric(values):

    if not values:
        return {
            "pattern": "unknown",
            "slope": 0,
            "confidence": 0
        }

    slope = compute_slope(values)

    if detect_spike(values):
        return {
            "pattern": "spike",
            "slope": slope,
            "confidence": 0.9
        }

    if detect_oscillation(values):
        return {
            "pattern": "oscillation",
            "slope": slope,
            "confidence": 0.8
        }

    if detect_plateau(values):
        return {
            "pattern": "stable",
            "slope": slope,
            "confidence": 0.85
        }

    if abs(slope) > SLOPE_THRESHOLD:
        return {
            "pattern": "gradual_increase" if slope > 0 else "gradual_decrease",
            "slope": slope,
            "confidence": 0.85
        }

    return {
        "pattern": "no_clear_pattern",
        "slope": slope,
        "confidence": 0.5
    }


# -------------------------------
# ENGINE ENTRY POINT
# -------------------------------
def temporal_analysis(history):

    if not history:
        return {
            "cpu": {"pattern": "unknown"},
            "memory": {"pattern": "unknown"},
            "disk": {"pattern": "unknown"}
        }

    cpu_values = get_recent_values(history, "cpu")
    mem_values = get_recent_values(history, "memory")
    disk_values = get_recent_values(history, "disk")

    cpu_analysis = analyze_metric(cpu_values)
    mem_analysis = analyze_metric(mem_values)
    disk_analysis = analyze_metric(disk_values)

    return {
        "cpu": cpu_analysis,
        "memory": mem_analysis,
        "disk": disk_analysis
    }
