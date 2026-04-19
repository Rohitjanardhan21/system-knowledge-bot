# ---------------------------------------------------------
# 🚗 VEHICLE CAUSAL ENGINE (ROOT CAUSE INFERENCE)
# ---------------------------------------------------------

def infer_vehicle_cause(signals, context):
    """
    Infers root cause based on signals + context
    """

    cause = {
        "type": "unknown",
        "confidence": 0.5,
        "details": []
    }

    # -----------------------------
    # 🚧 ROAD IMPACT (POTHOLE / BUMP)
    # -----------------------------
    if "impact_event" in signals:
        cause["type"] = "road_impact"
        cause["confidence"] = 0.9
        cause["details"].append("Sudden vibration + acoustic spike")

    # -----------------------------
    # 🔧 MECHANICAL ISSUE
    # -----------------------------
    elif "combined_anomaly" in signals:
        cause["type"] = "mechanical_stress"
        cause["confidence"] = 0.85
        cause["details"].append("High vibration + temperature")

    # -----------------------------
    # 🔥 ENGINE OVERHEATING
    # -----------------------------
    elif "thermal" in signals and context.get("risk_level") in ["high", "critical"]:
        cause["type"] = "thermal_overload"
        cause["confidence"] = 0.8
        cause["details"].append("High temperature trend")

    # -----------------------------
    # ⚠ PROGRESSIVE FAILURE
    # -----------------------------
    elif "predictive_failure" in signals:
        cause["type"] = "progressive_failure"
        cause["confidence"] = 0.95
        cause["details"].append("Degradation over time")

    # -----------------------------
    # 🛣 ROAD CONDITION
    # -----------------------------
    if context.get("road_type") == "rough":
        cause["details"].append("Rough road conditions detected")

    # -----------------------------
    # 🚦 SPEED FACTOR
    # -----------------------------
    if context.get("speed_class") in ["fast", "high_speed"]:
        cause["details"].append("High speed impact risk")

    return cause
