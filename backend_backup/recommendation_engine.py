class RecommendationEngine:

    def recommend(
        self,
        root,
        intent,
        global_state,
        anomalies=None,
        prediction=None
    ):
        anomalies = anomalies or []
        prediction = prediction or {}

        # --------------------------------------------------
        # SAFE DEFAULTS
        # --------------------------------------------------

        intent = intent or {}
        global_state = global_state or {}

        if not root:
            return {
                "message": "System stable. No action required.",
                "priority": "LOW",
                "confidence": 0.9,
                "actionable": False,
                "requires_approval": False
            }

        name = root.get("process", "unknown")
        cpu = root.get("cpu", 0)

        intent_type = intent.get("type", "unknown")

        anomaly_present = len(anomalies) > 0
        prediction_type = prediction.get("title")

        # --------------------------------------------------
        # 🧠 CONTEXT-AWARE SAFE CASES
        # --------------------------------------------------

        if intent_type == "user_browsing":
            return {
                "message": "High usage is due to active browsing behavior. No intervention recommended.",
                "priority": "LOW",
                "confidence": 0.85,
                "actionable": False,
                "requires_approval": False
            }

        if intent_type == "development":
            return {
                "message": "Development workload detected. Performance impact is expected.",
                "priority": "LOW",
                "confidence": 0.8,
                "actionable": False,
                "requires_approval": False
            }

        # --------------------------------------------------
        # 🔥 HIGH RISK SCENARIO (CPU + ANOMALY)
        # --------------------------------------------------

        if cpu > 85 and anomaly_present:
            return {
                "message": (
                    f"{name} is causing abnormal CPU spikes. "
                    "Intervention may be required to prevent instability."
                ),
                "priority": "CRITICAL",
                "confidence": 0.9,
                "actionable": True,

                # SAFE — NOT AUTO EXECUTED
                "suggested_action": {
                    "type": "terminate_process",
                    "target": name,
                    "reason": "abnormal_cpu_spike",
                    "impact": "may reduce system load",
                },

                "requires_approval": True,
                "human_note": "Verify before terminating critical processes."
            }

        # --------------------------------------------------
        # ⚠️ HIGH CPU WITHOUT ANOMALY
        # --------------------------------------------------

        if cpu > 80:
            return {
                "message": (
                    f"{name} is heavily loading CPU. "
                    "Consider reducing its usage if responsiveness is affected."
                ),
                "priority": "HIGH",
                "confidence": 0.75,
                "actionable": True,

                "suggested_action": {
                    "type": "limit_or_close",
                    "target": name,
                    "reason": "high_cpu_usage",
                    "impact": "improves responsiveness"
                },

                "requires_approval": True,
                "human_note": "Ensure this process is not mission-critical."
            }

        # --------------------------------------------------
        # ⚡ MEDIUM LOAD
        # --------------------------------------------------

        if cpu > 60:
            return {
                "message": f"{name} is consuming moderate CPU. Monitoring recommended.",
                "priority": "MEDIUM",
                "confidence": 0.7,
                "actionable": False,
                "requires_approval": False
            }

        # --------------------------------------------------
        # 🔮 FUTURE RISK (PREDICTION-AWARE)
        # --------------------------------------------------

        if prediction_type in ["rapid_increase", "overload"]:
            return {
                "message": (
                    "System load is predicted to increase. "
                    "Preemptive optimization may help avoid degradation."
                ),
                "priority": "MEDIUM",
                "confidence": prediction.get("confidence", 0.7),
                "actionable": True,

                "suggested_action": {
                    "type": "optimize_load",
                    "target": name,
                    "reason": "predicted_overload",
                    "impact": "prevents future instability"
                },

                "requires_approval": True,
                "human_note": "Validate prediction before taking action."
            }

        # --------------------------------------------------
        # ✅ DEFAULT SAFE STATE
        # --------------------------------------------------

        return {
            "message": "System operating within normal parameters.",
            "priority": "LOW",
            "confidence": 0.9,
            "actionable": False,
            "requires_approval": False
        }
