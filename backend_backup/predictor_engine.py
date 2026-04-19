class PredictorEngine:

    def predict(self, history, temporal):

        # -----------------------------------------
        # SAFETY
        # -----------------------------------------
        if not history:
            return {
                "type": "stable",
                "confidence": 0.5,
                "message": "No historical data available"
            }

        latest = history[-1]

        cpu = float(latest.get("cpu", 0))
        memory = float(latest.get("memory", 0))
        disk = float(latest.get("disk", 0))

        cpu_pattern = temporal.get("cpu", {}).get("pattern")
        mem_pattern = temporal.get("memory", {}).get("pattern")

        # -----------------------------------------
        # 🔥 SMOOTH CPU TREND
        # -----------------------------------------
        recent = history[-10:]
        cpu_values = [h.get("cpu", 0) for h in recent if isinstance(h.get("cpu"), (int, float))]

        if len(cpu_values) >= 2:
            trend = cpu_values[-1] - cpu_values[0]
        else:
            trend = 0

        # normalize trend
        trend_strength = min(1.0, abs(trend) / 50)

        # -----------------------------------------
        # 🔥 CASE 1: IMMEDIATE SPIKE
        # -----------------------------------------
        if cpu_pattern == "spike":
            return {
                "type": "cpu_spike",
                "confidence": 0.9,
                "message": f"Sudden CPU spike detected ({cpu:.1f}%)"
            }

        # -----------------------------------------
        # 🔥 CASE 2: GRADUAL INCREASE
        # -----------------------------------------
        if cpu_pattern == "gradual_increase" and trend > 5:

            future_cpu = cpu + trend * 0.5

            return {
                "type": "cpu_rising",
                "confidence": max(0.6, trend_strength),
                "message": f"CPU trending upward → may reach {round(future_cpu,1)}%"
            }

        # -----------------------------------------
        # 🔥 CASE 3: INSTABILITY
        # -----------------------------------------
        if cpu_pattern == "oscillation":
            return {
                "type": "cpu_instability",
                "confidence": 0.75,
                "message": "CPU usage is fluctuating (instability detected)"
            }

        # -----------------------------------------
        # 🔥 CASE 4: MEMORY PRESSURE
        # -----------------------------------------
        if mem_pattern == "gradual_increase" and memory > 70:
            return {
                "type": "memory_rising",
                "confidence": 0.8,
                "message": f"Memory usage increasing ({memory:.1f}%)"
            }

        # -----------------------------------------
        # 🔥 CASE 5: HIGH LOAD
        # -----------------------------------------
        if cpu > 90:
            return {
                "type": "high_cpu",
                "confidence": 0.9,
                "message": f"CPU critically high ({cpu:.1f}%)"
            }

        # -----------------------------------------
        # 🔥 CASE 6: MODERATE LOAD
        # -----------------------------------------
        if cpu > 60:
            return {
                "type": "moderate_load",
                "confidence": 0.7,
                "message": f"Moderate CPU load ({cpu:.1f}%)"
            }

        # -----------------------------------------
        # 🔥 DEFAULT (VERY IMPORTANT)
        # -----------------------------------------
        return {
            "type": "stable",
            "confidence": 0.6,
            "message": "System load is stable"
        }
