class ExplanationEngine:

    def generate(self, features, anomaly_score, cause, predictions):
        chain = []

        # SIGNAL LEVEL
        if features.get("vibration_intensity", 0) > 0.7:
            chain.append("High vibration detected")

        if features.get("thermal", 0) > 0.7:
            chain.append("Temperature rising")

        # SYSTEM LEVEL
        if anomaly_score > 1.5:
            chain.append("Anomaly detected in system behavior")

        # CAUSE LEVEL
        if cause:
            chain.append(f"Likely cause: {cause.get('type', 'unknown')}")

        # FUTURE LEVEL
        for p in predictions:
            chain.append(f"May lead to: {p['type']}")

        return chain


explanation_engine = ExplanationEngine()
