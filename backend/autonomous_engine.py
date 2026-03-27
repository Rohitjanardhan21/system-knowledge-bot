import time


class AutonomousEngine:

    def __init__(self):
        self.last_action_time = 0
        self.cooldown_seconds = 5

        # modes: manual | assist | autonomous
        self.mode = "autonomous"

    # -----------------------------------------
    # MAIN DECISION
    # -----------------------------------------
    def decide(self, prediction, causal, decision):

        # -----------------------------------------
        # MODE CONTROL
        # -----------------------------------------
        if self.mode == "manual":
            return None

        if not prediction:
            return None

        # -----------------------------------------
        # 🔥 EXTRACT CONTEXT
        # -----------------------------------------
        context = decision.get("context", "general")
        cpu = decision.get("cpu", 0)
        baseline = decision.get("baseline_cpu", 50)

        confidence = prediction.get("confidence", 0)
        risk = causal.get("system_risk", 0)
        cause = causal.get("primary_cause", {}).get("type")

        # -----------------------------------------
        # 🔥 CONTEXT-AWARE FILTERING
        # -----------------------------------------

        # 🚫 Do not interfere with gaming
        if context == "gaming":
            return None

        # 🚫 Avoid interrupting dev work unless critical
        if context == "development" and cpu < 95:
            return None

        # -----------------------------------------
        # 🔥 BASELINE-AWARE FILTERING
        # -----------------------------------------
        # Ignore normal load relative to user behavior
        if cpu < baseline + 20:
            return None

        # -----------------------------------------
        # 🔥 ADAPTIVE CONFIDENCE
        # -----------------------------------------
        # higher risk → slightly lower confidence requirement
        dynamic_threshold = 0.9 - (risk * 0.1)

        if confidence < dynamic_threshold:
            return None

        if risk < 0.5:
            return None

        # -----------------------------------------
        # 🔥 GLOBAL COOLDOWN
        # -----------------------------------------
        now = time.time()
        if now - self.last_action_time < self.cooldown_seconds:
            return None

        # -----------------------------------------
        # 🔥 ACTION MAPPING (SMARTER)
        # -----------------------------------------
        action = None
        reason = None

        if prediction["type"] in ["cpu_rising", "immediate_cpu_spike"]:

            if cause in ["cpu_overload", "sustained_compute_load"]:
                action = "throttle_background_processes"
                reason = "Preventing CPU spike"

        elif prediction["type"] == "memory_rising":

            if cause in ["memory_pressure"]:
                action = "free_memory_cache"
                reason = "Preventing memory pressure"

        elif prediction["type"] == "cpu_instability":

            action = "preemptive_cpu_control"
            reason = "Stabilizing CPU fluctuations"

        elif prediction["type"] == "high_cpu":

            # 🔥 only use aggressive action if extreme
            if cpu > 95:
                action = "kill_high_cpu_process"
                reason = "Critical CPU overload"

        # -----------------------------------------
        # ASSIST MODE (suggest only)
        # -----------------------------------------
        if self.mode == "assist":
            if action:
                return {
                    "action": action,
                    "reason": reason,
                    "mode": "suggested",
                    "context": context
                }
            return None

        # -----------------------------------------
        # AUTONOMOUS MODE (execute)
        # -----------------------------------------
        if action:
            self.last_action_time = now

            return {
                "action": action,
                "reason": reason,
                "mode": "auto",
                "context": context
            }

        return None
