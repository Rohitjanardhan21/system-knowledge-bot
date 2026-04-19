# ---------------------------------------------------------
# 🚗 FAILURE DIAGNOSIS ENGINE (ROBUST VERSION)
# ---------------------------------------------------------

def diagnose_failure(state):

    signals = state.get("signals", {}) or {}
    vision = state.get("vision", {}) or {}
    prediction = state.get("pre_impact", {}).get("prediction", {}) or {}

    issues = []

    # -----------------------------------------------------
    # 🔥 ENGINE OVERHEATING
    # -----------------------------------------------------
    thermal = signals.get("thermal", {})
    if isinstance(thermal, dict) and thermal.get("status") == "overheating":
        issues.append({
            "type": "engine_overheating",
            "severity": "HIGH",
            "confidence": 0.9,
            "recommendation": "stop_vehicle"
        })

    # -----------------------------------------------------
    # ⚙ MECHANICAL FAILURE
    # -----------------------------------------------------
    if signals.get("predictive_failure"):
        issues.append({
            "type": "mechanical_failure",
            "severity": "CRITICAL",
            "confidence": 0.95,
            "recommendation": "stop_immediately"
        })

    # -----------------------------------------------------
    # 🚧 ROAD IMPACT
    # -----------------------------------------------------
    if vision.get("object") and signals.get("impact_event"):
        issues.append({
            "type": "road_impact",
            "severity": "HIGH",
            "confidence": 0.9,
            "recommendation": "slow_down"
        })

    # -----------------------------------------------------
    # 🛞 TIRE INSTABILITY
    # -----------------------------------------------------
    vibration = signals.get("vibration", {})
    if isinstance(vibration, dict) and vibration.get("variance", 0) > 0.3:
        issues.append({
            "type": "tire_instability",
            "severity": "HIGH",
            "confidence": 0.85,
            "recommendation": "reduce_speed"
        })

    # -----------------------------------------------------
    # 🔋 ELECTRICAL ISSUE
    # -----------------------------------------------------
    if state.get("voltage_instability"):
        issues.append({
            "type": "electrical_fault",
            "severity": "MEDIUM",
            "confidence": 0.7,
            "recommendation": "check_system"
        })

    # -----------------------------------------------------
    # 🧠 PRIORITIZATION
    # -----------------------------------------------------
    if not issues:
        return {
            "issue": None,
            "severity": "LOW",
            "confidence": 0.0,
            "recommendation": "continue",
            "all_issues": []
        }

    severity_rank = {
        "LOW": 0,
        "MEDIUM": 1,
        "HIGH": 2,
        "CRITICAL": 3
    }

    # pick highest severity issue
    primary = sorted(
        issues,
        key=lambda x: severity_rank[x["severity"]],
        reverse=True
    )[0]

    # -----------------------------------------------------
    # 🧠 FINAL OUTPUT
    # -----------------------------------------------------
    return {
        "issue": primary["type"],
        "severity": primary["severity"],
        "confidence": primary["confidence"],
        "recommendation": primary["recommendation"],
        "all_issues": issues   # 🔥 multi-diagnosis support
    }
