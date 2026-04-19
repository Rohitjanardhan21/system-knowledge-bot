# ---------------------------------------------------------
# 🚗 VEHICLE HAZARD ENGINE (ROBUST + EXPLAINABLE)
# ---------------------------------------------------------

def safe_get(d, key, default=0):
    try:
        return d.get(key, default)
    except:
        return default


def compute_vehicle_hazard(
    anomaly_score,
    vehicle_cause,
    signals=None,
    pre_impact=None
):
    """
    🚗 Advanced Hazard Detection Engine

    Priority:
    1. Pre-impact prediction
    2. Signal fusion
    3. Anomaly scoring
    """

    signals = signals or {}

    evidence = []
    confidence = 0.5

    # -----------------------------------------------------
    # 🔴 1. PRE-IMPACT OVERRIDE
    # -----------------------------------------------------
    if isinstance(pre_impact, dict):
        hazard = pre_impact.get("hazard", {})

        level = hazard.get("level")

        if level in ["CRITICAL", "HIGH"]:
            return {
                "level": level,
                "action": hazard.get("action", "SLOW DOWN"),
                "source": "pre_impact_prediction",
                "confidence": 0.95,
                "evidence": ["Predicted obstacle ahead"]
            }

    # -----------------------------------------------------
    # 🧠 2. SIGNAL EXTRACTION (SAFE)
    # -----------------------------------------------------
    vibration = safe_get(signals, "vibration", {})
    thermal = safe_get(signals, "thermal", {})
    acoustic = safe_get(signals, "acoustic", {})

    vib_intensity = safe_get(vibration, "intensity", 0)
    vib_variance = safe_get(vibration, "variance", 0)

    thermal_level = safe_get(thermal, "level", 0)
    thermal_trend = safe_get(thermal, "trend", "stable")

    acoustic_energy = safe_get(acoustic, "energy", 0)

    # -----------------------------------------------------
    # 🚨 3. CRITICAL CONDITIONS
    # -----------------------------------------------------
    if (
        vib_intensity > 0.85 and
        vib_variance > 0.4 and
        thermal_level > 0.8
    ):
        evidence.append("High vibration + thermal spike")
        return {
            "level": "CRITICAL",
            "action": "STOP VEHICLE IMMEDIATELY",
            "source": "signal_fusion",
            "confidence": 0.9,
            "evidence": evidence
        }

    if vehicle_cause in ["engine_failure", "brake_failure"]:
        evidence.append(f"Detected {vehicle_cause}")
        return {
            "level": "CRITICAL",
            "action": "STOP VEHICLE IMMEDIATELY",
            "source": "vehicle_cause",
            "confidence": 0.95,
            "evidence": evidence
        }

    # -----------------------------------------------------
    # ⚠️ 4. HIGH RISK
    # -----------------------------------------------------
    if (
        vib_variance > 0.3 or
        acoustic_energy > 0.75 or
        thermal_trend == "rising"
    ):
        evidence.append("Abnormal signal pattern detected")
        return {
            "level": "HIGH",
            "action": "REDUCE SPEED AND INSPECT",
            "source": "signal_analysis",
            "confidence": 0.8,
            "evidence": evidence
        }

    if anomaly_score > 2.0:
        evidence.append("High anomaly score")
        return {
            "level": "HIGH",
            "action": "CHECK SYSTEM IMMEDIATELY",
            "source": "anomaly_score",
            "confidence": 0.75,
            "evidence": evidence
        }

    # -----------------------------------------------------
    # 🟡 5. MODERATE
    # -----------------------------------------------------
    if anomaly_score > 1.0:
        evidence.append("Moderate anomaly")
        return {
            "level": "MODERATE",
            "action": "MONITOR SYSTEM",
            "source": "anomaly_score",
            "confidence": 0.6,
            "evidence": evidence
        }

    if vib_intensity > 0.5:
        evidence.append("Moderate vibration")
        return {
            "level": "MODERATE",
            "action": "CHECK ROAD CONDITION",
            "source": "vibration",
            "confidence": 0.6,
            "evidence": evidence
        }

    # -----------------------------------------------------
    # 🟢 6. LOW (DEFAULT)
    # -----------------------------------------------------
    return {
        "level": "LOW",
        "action": "SYSTEM NORMAL",
        "source": "baseline",
        "confidence": 0.5,
        "evidence": ["No significant anomalies"]
    }
