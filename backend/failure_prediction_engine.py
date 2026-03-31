class FailurePredictionEngine:

    def predict(self, global_state, learning, root):

        cpu = global_state.get("cpu", 0)
        memory = global_state.get("memory", 0)

        anomalies = learning.get("anomalies", [])
        trends = learning.get("trends", [])
        patterns = learning.get("patterns", [])

        # ---------------------------------------------------------
        # 🔥 HIGH RISK (IMMINENT FAILURE)
        # ---------------------------------------------------------
        if cpu > 90:
            return {
                "status": "critical",
                "title": "CPU saturation imminent",
                "details": "System likely to freeze or throttle",
                "confidence": 0.95,
                "time_to_failure": "seconds"
            }

        if memory > 90:
            return {
                "status": "critical",
                "title": "Memory exhaustion imminent",
                "details": "Risk of application crashes",
                "confidence": 0.95,
                "time_to_failure": "seconds"
            }

        # ---------------------------------------------------------
        # 🔥 STRONG WARNING (VERY IMPORTANT)
        # ---------------------------------------------------------
        if anomalies:
            return {
                "status": "warning",
                "title": "Abnormal system behavior detected",
                "details": f"{anomalies[0]['metric']} deviation from baseline",
                "confidence": 0.85,
                "time_to_failure": "minutes"
            }

        # ---------------------------------------------------------
        # 🔥 TREND BASED PREDICTION
        # ---------------------------------------------------------
        if "CPU increasing trend" in trends:
            return {
                "status": "warning",
                "title": "CPU rising trend",
                "details": "System load increasing steadily",
                "confidence": 0.8,
                "time_to_failure": "minutes"
            }

        if "Memory increasing trend" in trends:
            return {
                "status": "warning",
                "title": "Memory usage rising",
                "details": "Possible memory leak or buildup",
                "confidence": 0.8,
                "time_to_failure": "minutes"
            }

        # ---------------------------------------------------------
        # 🔥 INSTABILITY DETECTION
        # ---------------------------------------------------------
        if "CPU instability (oscillation)" in patterns:
            return {
                "status": "warning",
                "title": "System instability detected",
                "details": "Fluctuating CPU may impact performance",
                "confidence": 0.75,
                "time_to_failure": "uncertain"
            }

        # ---------------------------------------------------------
        # ✅ HEALTHY
        # ---------------------------------------------------------
        return {
            "status": "healthy",
            "title": "System stable",
            "details": "No failure risks detected",
            "confidence": 0.7,
            "time_to_failure": None
        }
