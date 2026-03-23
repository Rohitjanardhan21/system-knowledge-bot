"""
Posture Engine

Determines overall system posture:

- stable
- stressed
- critical

Consumes:
- normalized metrics
- forecast output

Phase-5 compatible interface.
"""

# ---------------------------------------------------------
# Primary implementation (Phase-4 logic)
# ---------------------------------------------------------

def posture_from_metrics(metrics, forecast):
    """
    Decide posture based on live metrics + forecast.
    """

    cpu = metrics.get("cpu_pct", 0)
    mem = metrics.get("mem_pct", 0)
    disk = metrics.get("disk_pct", 0)

    risk = forecast.get("risk_score", 0)

    posture = "stable"

    # Live thresholds
    if cpu > 85 or mem > 85 or disk > 90:
        posture = "critical"
    elif cpu > 65 or mem > 65 or disk > 80:
        posture = "stressed"

    # Forecast override
    if risk > 70:
        posture = "critical"
    elif risk > 40 and posture != "critical":
        posture = "stressed"

    return posture


# ---------------------------------------------------------
# Phase-5 alias expected by routes
# ---------------------------------------------------------

def compute_posture(metrics, forecast):
    """
    Stable wrapper used by system_routes.
    """
    return posture_from_metrics(metrics, forecast)
