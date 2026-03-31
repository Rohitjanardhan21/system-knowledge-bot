# backend/explanation_engine.py
# ---------------------------------------------------------
# 🧠 EXPLANATION ENGINE (ZERO-HALLUCINATION SAFE)
# ---------------------------------------------------------

from typing import Dict, List


# ---------------------------------------------------------
# 🔍 EXTRACT EVIDENCE FROM STATE
# ---------------------------------------------------------
def extract_evidence(features: Dict) -> List[str]:

    evidence = []

    if not features:
        return evidence

    if features.get("compute", 0) > 80:
        evidence.append("High compute load detected")

    if features.get("thermal", 0) > 75:
        evidence.append("Elevated temperature observed")

    if features.get("vibration_intensity", 0) > 0.7:
        evidence.append("Abnormal vibration intensity")

    if features.get("acoustic_energy", 0) > 0.8:
        evidence.append("High acoustic energy (possible noise anomaly)")

    if features.get("electrical", 0) > 90:
        evidence.append("Electrical irregularity detected")

    return evidence


# ---------------------------------------------------------
# 🎯 CONFIDENCE CALIBRATION
# ---------------------------------------------------------
def calibrate_confidence(policy_value: float, evidence_count: int, anomaly_score: float):

    base = max(0.1, min(policy_value, 0.9))

    # Boost if anomaly is strong
    if anomaly_score > 1.5:
        base += 0.1

    # Reduce if weak evidence
    if evidence_count == 0:
        base -= 0.3
    elif evidence_count == 1:
        base -= 0.1

    return max(0.1, min(base, 0.95))


# ---------------------------------------------------------
# ⚠️ UNCERTAINTY DETECTION
# ---------------------------------------------------------
def detect_uncertainty(evidence_count: int, anomaly_score: float):

    if evidence_count == 0:
        return "insufficient_data"

    if anomaly_score < 0.5:
        return "low_signal"

    if evidence_count >= 3:
        return "high_confidence"

    return "moderate_confidence"


# ---------------------------------------------------------
# 🧠 MAIN EXPLANATION FUNCTION
# ---------------------------------------------------------
def generate_explanation(
    state: Dict,
    action: str,
    reward: float,
    policy_value: float
):

    features = state.get("features", {})
    anomaly_score = state.get("anomaly_score", 0)

    # -----------------------------------------------------
    # 🔍 EVIDENCE EXTRACTION
    # -----------------------------------------------------
    evidence = extract_evidence(features)

    # -----------------------------------------------------
    # 🎯 CONFIDENCE (CALIBRATED)
    # -----------------------------------------------------
    confidence = calibrate_confidence(
        policy_value,
        len(evidence),
        anomaly_score
    )

    # -----------------------------------------------------
    # ⚠️ UNCERTAINTY
    # -----------------------------------------------------
    uncertainty = detect_uncertainty(len(evidence), anomaly_score)

    # -----------------------------------------------------
    # 🧠 QUALITY (BASED ON REWARD)
    # -----------------------------------------------------
    outcome_quality = "effective" if reward > 0 else "ineffective"

    # -----------------------------------------------------
    # 📄 SAFE SUMMARY (NO GUESSING)
    # -----------------------------------------------------
    if evidence:
        summary = f"Action '{action}' selected based on observed system signals"
    else:
        summary = "Insufficient evidence to strongly justify action"

    # -----------------------------------------------------
    # 🔎 STRUCTURED REASONING (NO HALLUCINATION)
    # -----------------------------------------------------
    reasoning = {
        "policy_score": round(policy_value, 3),
        "anomaly_score": round(anomaly_score, 3),
        "evidence_count": len(evidence),
        "outcome_expectation": outcome_quality
    }

    # -----------------------------------------------------
    # 🧾 FINAL OUTPUT
    # -----------------------------------------------------
    return {
        "summary": summary,
        "action": action,
        "evidence": evidence,
        "reasoning": reasoning,
        "confidence": round(confidence, 2),
        "uncertainty": uncertainty,
        "validated": len(evidence) > 0
    }
