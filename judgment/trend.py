
from __future__ import annotations

import json


def _values(history, section, key):
    values = []

    for sample in history:
        value = sample.get(section, {}).get(key)

        if isinstance(value, (int, float)):
            values.append(float(value))

    return values


def _classify(values, tolerance=0.5):
    if len(values) < 3:
        return "insufficient-data"

    deltas = [
        values[i] - values[i - 1]
        for i in range(1, len(values))
    ]

    rising = sum(delta > tolerance for delta in deltas)
    falling = sum(delta < -tolerance for delta in deltas)
    stable = len(deltas) - rising - falling

    total = len(deltas)

    if rising / total >= 0.67:
        return "worsening"

    if falling / total >= 0.67:
        return "recovering"

    if stable / total >= 0.67:
        return "persistent"

    return "volatile"


def analyze_history(history):
    return {
        "cpu": {
            "trend": _classify(
                _values(history, "cpu", "usage_percent")
            )
        },
        "memory": {
            "trend": _classify(
                _values(history, "memory", "used_mb")
            )
        },
        "disk": {
            "trend": _classify(
                _values(history, "disk", "used_percent")
            )
        },
    }


if __name__ == "__main__":
    with open(r".\state\history.json", encoding="utf-8") as f:
        history = json.load(f)

    print("=== TREND ANALYSIS ===")

    result = analyze_history(history)

    for subsystem, data in result.items():
        print(
            f"{subsystem:8} -> "
            f"{data['trend']}"
        )
