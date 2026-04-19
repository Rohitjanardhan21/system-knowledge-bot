class SystemStoryEngine:

    def generate(self, metrics, anomalies, causal_graph, decision, history=None, forecast=None):

        story = []

        cpu = metrics.get("cpu", 0)
        mem = metrics.get("memory", 0)
        disk = metrics.get("disk", 0)

        # --- CURRENT STATE ---
        story.append(
            f"System snapshot indicates CPU at {cpu:.1f}%, memory at {mem:.1f}%, and disk usage at {disk:.1f}%."
        )

        # --- TEMPORAL ANALYSIS ---
        if history and len(history) >= 3:
            try:
                cpu_trend = history[-1]["cpu"] - history[-3]["cpu"]
                mem_trend = history[-1]["memory"] - history[-3]["memory"]

                if cpu_trend > 5:
                    story.append("CPU usage has shown a rising trend over recent intervals.")
                elif cpu_trend < -5:
                    story.append("CPU usage has been decreasing, indicating load stabilization.")

                if mem_trend > 5:
                    story.append("Memory consumption is increasing, suggesting accumulating load.")
                elif mem_trend < -5:
                    story.append("Memory usage is declining, indicating recovery.")

            except Exception:
                story.append("Temporal analysis could not be fully evaluated.")

        # --- STATE INTERPRETATION ---
        risk_score = 0

        if cpu > 85:
            risk_score += 2
        if mem > 85:
            risk_score += 2
        if anomalies:
            risk_score += 1

        if risk_score >= 4:
            story.append("System is in a high-risk state with potential instability.")
        elif risk_score >= 2:
            story.append("System is under moderate stress and should be monitored.")
        else:
            story.append("System is operating within stable conditions.")

        # --- ANOMALY ANALYSIS ---
        if anomalies:
            story.append(
                f"{len(anomalies)} anomaly signals detected, indicating deviation from learned baseline."
            )
        else:
            story.append("No anomalies detected relative to baseline behavior.")

        # --- CAUSAL ANALYSIS ---
        if causal_graph:
            try:
                key, value = list(causal_graph.items())[0]
                confidence = value.get("confidence", 0)
                relation_type = value.get("type", "correlation")

                src, tgt = key.split("->") if "->" in key else (key, "")

                if relation_type == "lagged_effect":
                    story.append(
                        f"Lag-based dependency detected: changes in {src} precede changes in {tgt} "
                        f"(confidence {confidence:.2f})."
                    )
                else:
                    story.append(
                        f"Correlation observed involving {key} with confidence {confidence:.2f}."
                    )

            except Exception:
                story.append("Causal inference remains inconclusive.")

        # --- FORECAST / FUTURE AWARENESS ---
        if forecast:
            try:
                future_cpu = forecast.get("cpu")
                future_mem = forecast.get("memory")

                if future_cpu and future_cpu > cpu + 5:
                    story.append("Forecast indicates CPU load may increase in the near future.")

                if future_mem and future_mem > mem + 5:
                    story.append("Forecast suggests rising memory pressure ahead.")

            except Exception:
                story.append("Forecast signals are currently uncertain.")

        # --- DECISION ENGINE ---
        if decision:
            action = decision.get("action", "unknown")
            confidence = decision.get("confidence", 0)
            reason = decision.get("reason", "No reasoning provided")
            executable = decision.get("executable", False)

            if action == "no_action":
                story.append(
                    f"No intervention required. System remains stable (confidence {confidence:.2f})."
                )
            else:
                exec_text = (
                    "Action is executable and can be triggered automatically."
                    if executable else
                    "Action is advisory and requires manual confirmation."
                )

                story.append(
                    f"Decision engine recommends '{action}' based on: {reason}. "
                    f"Confidence level is {confidence:.2f}. {exec_text}"
                )

        # --- SELF-AWARENESS LAYER ---
        story.append(
            "This analysis integrates temporal patterns, anomaly detection, and statistical relationships "
            "to form a probabilistic understanding of system behavior."
        )

        story.append(
            "All conclusions are uncertainty-aware and do not imply deterministic causation."
        )

        return " ".join(story)
