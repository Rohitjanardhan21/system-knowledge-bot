# backend/vehicle_causal_engine.py

def infer_vehicle_cause(features):

    vibration = features.get("vibration_intensity", 0)
    thermal = features.get("thermal", 0)
    acoustic = features.get("acoustic_energy", 0)

    evidence = []

    # 🛵 / 🚗 ENGINE IMBALANCE
    if vibration > 0.75:
        evidence.append("high vibration")
        return {
            "type": "engine_imbalance",
            "severity": "high",
            "evidence": evidence
        }

    # 🔥 OVERHEATING
    if thermal > 90:
        evidence.append("high engine temperature")
        return {
            "type": "engine_overheating",
            "severity": "critical",
            "evidence": evidence
        }

    # 🔊 ABNORMAL SOUND
    if acoustic > 0.85:
        evidence.append("abnormal acoustic signature")
        return {
            "type": "mechanical_noise",
            "severity": "medium",
            "evidence": evidence
        }

    return {
        "type": "normal",
        "severity": "low",
        "evidence": []
    }
