# ---------------------------------------------------------
# 🔥 UNIVERSAL FUSION ENGINE (OS + VEHICLE SAFE)
# ---------------------------------------------------------

def fuse_intelligence(state):

    fusion = {}

    # SAFE EXTRACTION
    vision = state.get("vision") or {}
    signals = state.get("signals") or {}
    pre = state.get("pre_impact") or {}
    prediction = pre.get("prediction") or {}
    hazard = state.get("hazard") or {}

    risk_score = 0.0

    # -----------------------------------------------------
    # 🚧 VISUAL DETECTION (VEHICLE ONLY)
    # -----------------------------------------------------
    if vision.get("object"):
        fusion["visual"] = {
            "object": vision.get("object"),
            "confidence": float(vision.get("confidence", 0))
        }
        risk_score += 0.3

    # -----------------------------------------------------
    # 🚨 IMPACT CONFIRMATION
    # -----------------------------------------------------
    if vision.get("object") and signals.get("impact_event"):
        fusion["confirmed_event"] = {
            "type": "road_impact",
            "confidence": 0.95,
            "action": "emergency_brake"
        }
        risk_score += 0.9

    elif vision.get("object"):
        fusion["visual_only"] = {
            "type": vision.get("object"),
            "confidence": 0.6
        }

    # -----------------------------------------------------
    # 🔥 INTERNAL FAILURE (WORKS FOR BOTH SYSTEMS)
    # -----------------------------------------------------
    if signals.get("predictive_failure"):
        fusion["failure"] = {
            "type": "system_failure",
            "severity": "critical"
        }
        risk_score += 0.8

    # -----------------------------------------------------
    # ⚙ ANOMALY / STRESS
    # -----------------------------------------------------
    if signals.get("combined_anomaly"):
        fusion["stress"] = {
            "type": "system_stress",
            "severity": "high"
        }
        risk_score += 0.5

    # -----------------------------------------------------
    # ⏱️ PRE-IMPACT (SAFE)
    # -----------------------------------------------------
    if isinstance(prediction, dict) and prediction:

        tti = prediction.get("time_to_impact", 5)

        try:
            tti = float(tti)
        except:
            tti = 5

        if tti < 1:
            fusion["immediate_collision"] = {
                "severity": "critical",
                "action": "emergency_brake"
            }
            risk_score += 1.0

        elif tti < 2:
            fusion["collision_warning"] = {
                "severity": "high"
            }
            risk_score += 0.7

    # -----------------------------------------------------
    # 🧠 GENERIC SYSTEM ANOMALY (OS SUPPORT)
    # -----------------------------------------------------
    anomaly = state.get("anomaly_score", 0)

    try:
        anomaly = float(anomaly)
    except:
        anomaly = 0

    if anomaly > 2:
        fusion["system_anomaly"] = {
            "severity": "high"
        }
        risk_score += 0.6

    # -----------------------------------------------------
    # 🧠 FINAL RISK SCORE
    # -----------------------------------------------------
    fusion["risk_score"] = round(min(1.0, risk_score), 2)

    # -----------------------------------------------------
    # 🎯 FINAL DECISION
    # -----------------------------------------------------
    if fusion.get("immediate_collision"):
        fusion["final_decision"] = "emergency_brake"

    elif fusion.get("confirmed_event"):
        fusion["final_decision"] = "slow_down"

    elif fusion.get("failure"):
        fusion["final_decision"] = "investigate"

    elif fusion["risk_score"] > 0.7:
        fusion["final_decision"] = "caution"

    else:
        fusion["final_decision"] = "maintain_state"

    return fusion
