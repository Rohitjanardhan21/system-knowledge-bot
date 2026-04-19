# backend/vehicle_system/predictive_engine.py

class PredictiveEngine:

    def __init__(self):
        self.history = []

    def update_history(self, signals):
        self.history.append(signals)
        if len(self.history) > 50:
            self.history.pop(0)

    def predict(self):
        if len(self.history) < 5:
            return {"prediction": None}

        temps = [h.get("temperature", 0) for h in self.history]
        vibrations = [h.get("vibration", 0) for h in self.history]

        temp_trend = temps[-1] - temps[0]
        vib_trend = vibrations[-1] - vibrations[0]

        predictions = []

        if temp_trend > 10:
            predictions.append({
                "type": "engine_overheating",
                "time_to_risk": "2-5 min",
                "confidence": 0.8
            })

        if vib_trend > 5:
            predictions.append({
                "type": "road_roughness_or_damage",
                "time_to_risk": "immediate",
                "confidence": 0.7
            })

        return {"predictions": predictions}


predictive_engine = PredictiveEngine()
