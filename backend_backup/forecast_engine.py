"""
Forecast Engine

Consumes trend outputs and produces:

- risk_score (0–100)
- cpu_projection
- memory_projection
- disk_projection
- likely_posture

This module is Phase-5 compatible.
"""

# ---------------------------------------------------------
# Primary implementation (your existing logic)
# ---------------------------------------------------------

def forecast_from_trends(trends):

    if not trends:
        return {
            "risk_score": 0,
            "cpu_projection": 0,
            "memory_projection": 0,
            "disk_projection": 0,
            "likely_posture": "stable",
        }

    cpu = trends.get("cpu_slope", 0)
    mem = trends.get("memory_slope", 0)
    disk = trends.get("disk_slope", 0)

    risk = 0

    if cpu > 10:
        risk += 30
    if mem > 10:
        risk += 30
    if disk > 5:
        risk += 20

    likely = "stable"

    if risk > 60:
        likely = "critical"
    elif risk > 30:
        likely = "stressed"

    return {
        "risk_score": min(risk, 100),
        "cpu_projection": round(cpu, 2),
        "memory_projection": round(mem, 2),
        "disk_projection": round(disk, 2),
        "likely_posture": likely,
    }


# ---------------------------------------------------------
# Phase-5 interface alias
# ---------------------------------------------------------

def compute_forecast(trends):
    """
    Stable wrapper used by system_routes and future phases.
    """
    return forecast_from_trends(trends)
