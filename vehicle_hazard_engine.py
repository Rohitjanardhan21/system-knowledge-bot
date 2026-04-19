# backend/vehicle_hazard_engine.py

def compute_vehicle_hazard(anomaly_score, cause, signals):

    risk = 0

    # Base anomaly
    if anomaly_score > 2:
        risk += 3
    elif anomaly_score > 1:
        risk += 2
    elif anomaly_score > 0.5:
        risk += 1

    # Cause severity
    if cause in ["engine_overheating"]:
        risk += 3
    elif cause in ["engine_imbalance"]:
        risk += 2
    elif cause in ["mechanical_noise"]:
        risk += 1

    # Hidden signals
    if signals.get("latent_instability"):
        risk += 2

    if signals.get("acoustic_spike"):
        risk += 1

    if signals.get("thermal_trend", 0) > 0.05:
        risk += 2

    # -------------------------------------------------
    # FINAL CLASSIFICATION
    # -------------------------------------------------
    if risk >= 6:
        return {
            "level": "CRITICAL",
            "action": "STOP VEHICLE IMMEDIATELY"
        }

    elif risk >= 4:
        return {
            "level": "HIGH",
            "action": "INSPECT VEHICLE SOON"
        }

    elif risk >= 2:
        return {
            "level": "MODERATE",
            "action": "MONITOR CONDITION"
        }

    return {
        "level": "LOW",
        "action": "NORMAL OPERATION"
    }
