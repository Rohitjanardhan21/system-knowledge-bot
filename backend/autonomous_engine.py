# backend/autonomous_engine.py

import time
from backend.decision_guard import guard_decision
from backend.simulation_engine import SimulationEngine  # ✅ FIXED
from backend.policy_engine import is_action_allowed


class AutonomousEngine:

    def __init__(self):
        self.last_action_time = 0
        self.cooldown_seconds = 5

        self.mode = "autonomous"

        self.max_actions_per_min = 3
        self.action_history = []

        self.simulator = SimulationEngine()  # ✅ NEW

    # -----------------------------------------
    # 🔥 RATE LIMIT
    # -----------------------------------------
    def _rate_limited(self):
        now = time.time()

        self.action_history = [
            t for t in self.action_history if now - t < 60
        ]

        return len(self.action_history) >= self.max_actions_per_min

    # -----------------------------------------
    # MAIN DECISION
    # -----------------------------------------
    def decide(self, prediction, causal, decision):

        if self.mode == "manual":
            return None

        if not prediction:
            return None

        context = decision.get("context", "general")
        cpu = decision.get("cpu", 0)
        baseline = decision.get("baseline_cpu", 50)
        duration = decision.get("duration_seconds", 0)

        confidence = prediction.get("confidence", 0)
        risk = causal.get("system_risk", 0)

        primary = causal.get("primary_cause", {})
        cause = primary.get("type")
        contributors = primary.get("contributors", [])

        # -----------------------------------------
        # 🧠 DECISION TRACE (NEW)
        # -----------------------------------------
        trace = []

        # -----------------------------------------
        # 🔥 CONTEXT FILTER
        # -----------------------------------------
        if context == "gaming":
            return {
                "status": "blocked",
                "reason": "Gaming session detected — no interference",
                "decision_trace": ["Blocked: gaming context"],
                "requires_user": False
            }

        if context == "critical":
            return {
                "status": "blocked",
                "reason": "Critical workload detected — protected",
                "decision_trace": ["Blocked: critical context"],
                "requires_user": False
            }

        if context == "development" and cpu < 95:
            return None

        # -----------------------------------------
        # 🔥 BASELINE + DURATION
        # -----------------------------------------
        if cpu < baseline + 20:
            trace.append("CPU within baseline")
            return None

        if duration < 30:
            trace.append("Short spike ignored")
            return None

        # -----------------------------------------
        # 🔥 CONFIDENCE + RISK
        # -----------------------------------------
        dynamic_threshold = 0.9 - (risk * 0.1)

        if confidence < dynamic_threshold:
            trace.append("Low confidence")
            return None

        if risk < 0.5:
            trace.append("Low risk")
            return None

        # -----------------------------------------
        # 🔥 COOLDOWN
        # -----------------------------------------
        now = time.time()
        if now - self.last_action_time < self.cooldown_seconds:
            return None

        # -----------------------------------------
        # 🔥 RATE LIMIT
        # -----------------------------------------
        if self._rate_limited():
            return {
                "status": "blocked",
                "reason": "Rate limited",
                "decision_trace": ["Too many actions recently"],
                "requires_user": True
            }

        # -----------------------------------------
        # 🔥 ACTION MAPPING
        # -----------------------------------------
        action = None
        reason = None

        if prediction["type"] in ["cpu_rising", "immediate_cpu_spike"]:
            if cause in ["cpu_overload", "sustained_compute_load"]:
                action = {
                    "type": "throttle_background_processes"
                }
                reason = "Reducing background load"

        elif prediction["type"] == "memory_rising":
            action = {"type": "free_memory_cache"}
            reason = "Reducing memory usage"

        elif prediction["type"] == "cpu_instability":
            action = {"type": "preemptive_cpu_control"}
            reason = "Stabilizing CPU"

        elif prediction["type"] == "high_cpu":
            if cpu > 95:
                action = {
                    "type": "kill_high_cpu_process",
                    "target_name": "high_cpu_process"
                }
                reason = "Critical CPU overload"

        if not action:
            return None

        trace.append(f"Action selected: {action['type']}")

        # -----------------------------------------
        # 🔥 POLICY ENGINE (FIXED)
        # -----------------------------------------
        allowed, policy_reason = is_action_allowed(
            action["type"],
            context=context,
            target_name=action.get("target_name")
        )

        if not allowed:
            return {
                "status": "blocked",
                "reason": policy_reason,
                "action": action,
                "decision_trace": trace + [policy_reason],
                "requires_user": True
            }

        # -----------------------------------------
        # 🔥 GUARD
        # -----------------------------------------
        state = {
            "confidence": confidence,
            "context": context,
            "persistent_issue": duration > 60,
            "cpu": cpu
        }

        guard = guard_decision(state, action)

        if not guard["allowed"]:
            return {
                "status": "blocked",
                "reason": guard["reasons"],
                "action": action,
                "decision_trace": trace + ["Guard blocked"],
                "requires_user": True
            }

        # -----------------------------------------
        # 🔥 SIMULATION (FIXED)
        # -----------------------------------------
        simulated = self.simulator.apply_action(
            {"cpu": cpu, "memory": decision.get("memory", 0), "disk": decision.get("disk", 0)},
            action["type"]
        )

        score = self.simulator.evaluate_state(simulated)

        if score < 0:
            return {
                "status": "blocked_simulation",
                "reason": "Simulation predicted negative outcome",
                "action": action,
                "decision_trace": trace + ["Simulation blocked"],
                "requires_user": True
            }

        trace.append(f"Simulation score: {score}")

        # -----------------------------------------
        # 🔥 ASSIST MODE
        # -----------------------------------------
        if self.mode == "assist":
            return {
                "status": "suggested",
                "action": action,
                "reason": reason,
                "contributors": contributors,
                "decision_trace": trace,
                "requires_user": True
            }

        # -----------------------------------------
        # 🔥 AUTO MODE
        # -----------------------------------------
        self.last_action_time = now
        self.action_history.append(now)

        return {
            "status": "approved",
            "action": action,
            "reason": reason,
            "contributors": contributors,
            "decision_trace": trace,
            "mode": "auto"
        }
