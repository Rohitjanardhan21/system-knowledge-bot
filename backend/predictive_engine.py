from statistics import mean

class PredictiveEngine:

    # -----------------------------------------
    # 🔮 CPU FORECAST (TREND BASED)
    # -----------------------------------------
    def forecast_cpu(self, history):
        if len(history) < 6:
            return None

        values = [h["cpu"] for h in history[-6:]]

        # simple trend (linear slope)
        slope = (values[-1] - values[0]) / len(values)

        next_values = []

        current = values[-1]

        for i in range(5):  # 🔮 predict next 5 steps
            current = current + slope
            next_values.append(max(0, min(100, current)))

        return next_values
