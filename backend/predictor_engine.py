class PredictorEngine:

    def predict(self, history, temporal):

        # -----------------------------------------
        # SAFETY
        # -----------------------------------------
        if not history:
            return None

        latest = history[-1]

        cpu = float(latest.get("cpu", 0))
        memory = float(latest.get("memory", 0))
        disk = float(latest.get("disk", 0))

        cpu_pattern = temporal.get("cpu", {}).get("pattern")
        mem_pattern = temporal.get("memory", {}).get("pattern")

        # -----------------------------------------
        # 🔥 CASE 1: IMMEDIATE SPIKE
        # -----------------------------------------
        if cpu_pattern == "spike":
            return {
                "type": "immediate_cpu_spike",
                "confidence": 0.95,
                "message": f"Sudden CPU spike detected ({cpu:.1f}%)"
            }

        # -----------------------------------------
        # 🔥 CASE 2: GRADUAL INCREASE (MOST IMPORTANT)
        # -----------------------------------------
        if cpu_pattern == "gradual_increase":

            # compute trend manually
            values = [h.get("cpu", 0) for h in history[-10:]]
            if len(values) >= 2:
                trend = values[-1] - values[0]
            else:
                trend = 0

            future_cpu = cpu + trend * 0.5

            if future_cpu > 85:
                return {
                    "type": "cpu_rising",
                    "confidence": min(1.0, trend / 25),
                    "message": f"CPU trending upward → may reach {round(future_cpu,1)}%"
                }

        # -----------------------------------------
        # 🔥 CASE 3: OSCILLATION (INSTABILITY)
        # -----------------------------------------
        if cpu_pattern == "oscillation":
            return {
                "type": "cpu_instability",
                "confidence": 0.8,
                "message": "CPU instability detected (oscillation)"
            }

        # -----------------------------------------
        # 🔥 CASE 4: MEMORY PRESSURE (CROSS-METRIC)
        # -----------------------------------------
        if mem_pattern == "gradual_increase" and memory > 70:
            return {
                "type": "memory_rising",
                "confidence": 0.8,
                "message": f"Memory usage increasing ({memory:.1f}%)"
            }

        # -----------------------------------------
        # 🔥 CASE 5: HIGH LOAD WARNING
        # -----------------------------------------
        if cpu > 90:
            return {
                "type": "high_cpu",
                "confidence": 0.9,
                "message": f"CPU critically high ({cpu:.1f}%)"
            }

        # -----------------------------------------
        # DEFAULT
        # -----------------------------------------
        return None
