class FutureEngine:

    def simulate(self, features):
        risk = (
            features.get("vibration_intensity", 0) * 0.5 +
            features.get("thermal", 0) * 0.5
        )

        if risk > 0.7:
            return {
                "next_5s": "Risk increasing",
                "next_10s": "Potential hazard",
                "confidence": 0.8
            }

        return {
            "next_5s": "Stable",
            "next_10s": "No immediate risk",
            "confidence": 0.9
        }


future_engine = FutureEngine()
