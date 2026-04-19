# ---------------------------------------------------------
# 🚗 VEHICLE SIGNAL ANALYZER (PRODUCTION + ROBUST VERSION)
# ---------------------------------------------------------

import numpy as np
from datetime import datetime


# ---------------------------------------------------------
# 🧠 SAFE UTILS
# ---------------------------------------------------------

def safe_float(x):
    try:
        val = float(x)
        if np.isnan(val) or np.isinf(val):
            return 0.0
        return val
    except:
        return 0.0


def compute_trend(values):
    if len(values) < 2:
        return 0.0
    try:
        x = np.arange(len(values))
        y = np.array(values)
        return float(np.polyfit(x, y, 1)[0])
    except:
        return 0.0


def compute_variance(values):
    if len(values) < 2:
        return 0.0
    return float(np.var(values))


def detect_spike(current, history, threshold=0.2):
    if not history:
        return False
    avg = np.mean(history)
    return abs(current - avg) > threshold


# ---------------------------------------------------------
# 🔥 MAIN ANALYZER
# ---------------------------------------------------------

def analyze_vehicle_signals(current_features, history):

    signals = {}
    confidence = 0.5

    # ---------------- SAFE EXTRACTION ----------------
    vib = safe_float(current_features.get("vibration_intensity", 0))
    temp = safe_float(current_features.get("thermal", 0))
    acoustic = safe_float(current_features.get("acoustic_energy", 0))

    vib_hist = [safe_float(h.get("vibration_intensity", 0)) for h in history]
    temp_hist = [safe_float(h.get("thermal", 0)) for h in history]
    ac_hist = [safe_float(h.get("acoustic_energy", 0)) for h in history]

    # -----------------------------------------------------
    # 🔧 VIBRATION ANALYSIS
    # -----------------------------------------------------
    vib_var = compute_variance(vib_hist)
    vib_trend = compute_trend(vib_hist)
    vib_spike = detect_spike(vib, vib_hist)

    if vib > 0.7 or vib_var > 0.15:
        signals["vibration"] = {
            "value": round(vib, 3),
            "variance": round(vib_var, 3),
            "trend": round(vib_trend, 3),
            "spike": vib_spike,
            "status": "unstable" if vib_var > 0.2 else "elevated",
            "severity": "high" if vib > 0.85 else "medium"
        }
        confidence += 0.1

    # -----------------------------------------------------
    # 🌡️ THERMAL ANALYSIS
    # -----------------------------------------------------
    temp_trend = compute_trend(temp_hist)
    temp_spike = detect_spike(temp, temp_hist)

    if temp > 0.75 or temp_trend > 0.01:
        signals["thermal"] = {
            "value": round(temp, 3),
            "trend": round(temp_trend, 4),
            "spike": temp_spike,
            "status": "overheating" if temp > 0.85 else "rising",
            "severity": "high" if temp > 0.9 else "medium"
        }
        confidence += 0.1

    # -----------------------------------------------------
    # 🔊 ACOUSTIC ANALYSIS
    # -----------------------------------------------------
    ac_var = compute_variance(ac_hist)
    ac_spike = detect_spike(acoustic, ac_hist)

    if acoustic > 0.7 or ac_spike:
        signals["acoustic"] = {
            "value": round(acoustic, 3),
            "variance": round(ac_var, 3),
            "spike": ac_spike,
            "status": "abnormal",
            "severity": "medium" if acoustic < 0.85 else "high"
        }
        confidence += 0.1

    # -----------------------------------------------------
    # 🧠 COMBINED SIGNALS
    # -----------------------------------------------------
    if vib > 0.6 and temp > 0.7:
        signals["combined_anomaly"] = {
            "type": "mechanical_stress",
            "description": "High vibration + rising temperature",
            "severity": "high"
        }
        confidence += 0.15

    if vib_spike and ac_spike:
        signals["impact_event"] = {
            "type": "road_impact",
            "description": "Possible pothole or bump",
            "severity": "high"
        }
        confidence += 0.2

    # -----------------------------------------------------
    # 📈 PREDICTIVE FAILURE
    # -----------------------------------------------------
    if temp_trend > 0.02 and vib_trend > 0.01:
        signals["predictive_failure"] = {
            "type": "progressive_degradation",
            "description": "System degrading over time",
            "severity": "critical"
        }
        confidence += 0.25

    # -----------------------------------------------------
    # 🔥 FINAL SUMMARY
    # -----------------------------------------------------
    overall_severity = "low"

    if "predictive_failure" in signals:
        overall_severity = "critical"
    elif "impact_event" in signals or "combined_anomaly" in signals:
        overall_severity = "high"
    elif signals:
        overall_severity = "medium"

    return {
        "signals": signals,
        "confidence": round(min(confidence, 0.95), 2),
        "severity": overall_severity,
        "timestamp": datetime.utcnow().isoformat()
    }
