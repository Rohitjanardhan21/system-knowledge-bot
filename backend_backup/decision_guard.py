PROTECTED_PROCESSES = ["code", "chrome", "explorer", "system", "svchost"]

def guard_decision(state, action):

    reasons = []

    # ---------------- CONFIDENCE ----------------
    if state.get("confidence", 0) < 0.6:
        reasons.append("low_confidence")

    # ---------------- CONTEXT ----------------
    if state.get("context") in ["gaming", "rendering"]:
        reasons.append("user_busy")

    # ---------------- TEMPORAL ----------------
    if not state.get("persistent_issue", False):
        reasons.append("temporary_spike")

    # ---------------- SAFETY ----------------
    if action.get("type") == "kill_process":
        target = action.get("target_name", "").lower()

        if target in PROTECTED_PROCESSES:
            reasons.append("protected_process")

    # ---------------- FINAL ----------------
    if reasons:
        return {
            "allowed": False,
            "reasons": reasons,
            "risk": "HIGH"
        }

    return {
        "allowed": True,
        "risk": "LOW"
    }
