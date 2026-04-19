def generate_agent_response(system_data, query=None, memory=None):

    cause = system_data.get("primary_cause", {})
    risk = system_data.get("system_risk", 0)

    cpu = system_data.get("cpu", 0)

    # -------------------------------------------------
    # INTENT DETECTION (simple but powerful)
    # -------------------------------------------------
    q = (query or "").lower()

    if "what changed" in q and memory:
        return memory.detect_change(system_data)

    if "history" in q and memory:
        hist = memory.get_recent()
        return f"You have {len(hist)} recent system events recorded."

    # -------------------------------------------------
    # DEFAULT RESPONSE
    # -------------------------------------------------
    if not cause:
        return "System is stable. No major issues detected."

    process = cause.get("caused_by")
    confidence = cause.get("confidence", 0)
    action = cause.get("recommended_action")

    msg = ""

    if process:
        msg += f"CPU is high mainly due to {process}. "
    else:
        msg += f"System shows {cause.get('type')}. "

    msg += f"Confidence: {round(confidence * 100)}%. "

    if risk > 0.7:
        msg += "This is high risk. "

    if action:
        msg += f"Suggested action: {action.replace('_', ' ')}."

    return msg
