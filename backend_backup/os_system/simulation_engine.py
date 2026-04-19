import copy
import random


class SimulationEngine:

    # -------------------------------------------------
    def __init__(self, causal_graph=None):
        self.graph = causal_graph or {}

        self.MAX_CHANGE = 40
        self.NOISE_RANGE = (0.9, 1.1)

    # -------------------------------------------------
    # 🔧 SAFE GET
    # -------------------------------------------------
    def _get(self, state, key):
        try:
            return float(state.get(key, 0))
        except:
            return 0.0

    # -------------------------------------------------
    # APPLY ACTION
    # -------------------------------------------------
    def apply_action(self, state, action):

        new_state = {
            "cpu": self._get(state, "cpu"),
            "memory": self._get(state, "memory"),
            "disk": self._get(state, "disk")
        }

        def safe_delta(v):
            return max(-self.MAX_CHANGE, min(self.MAX_CHANGE, v))

        # ---------------- ACTION EFFECTS ----------------
        if action == "throttle_background_processes":
            new_state["cpu"] += safe_delta(-20)
            new_state["memory"] += safe_delta(-5)

        elif action == "free_memory_cache":
            new_state["memory"] += safe_delta(-25)

        elif action == "reduce_disk_io":
            new_state["disk"] += safe_delta(-20)

        elif action == "kill_high_cpu_process":
            new_state["cpu"] += safe_delta(-35)
            new_state["memory"] += safe_delta(-10)

        elif action == "preemptive_cpu_control":
            new_state["cpu"] += safe_delta(-15)

        elif action == "safe_mode":
            new_state["cpu"] += safe_delta(-30)
            new_state["memory"] += safe_delta(-20)
            new_state["disk"] += safe_delta(-10)

        # ---------------- CAUSAL PROPAGATION ----------------
        if isinstance(self.graph, dict):
            for src, edges in self.graph.items():
                if src in new_state:
                    for tgt, weight in edges.items():
                        if tgt in new_state:

                            noise = random.uniform(*self.NOISE_RANGE)
                            impact = new_state[src] * weight * 0.05 * noise
                            impact = safe_delta(impact)

                            new_state[tgt] += impact

        return self._normalize(new_state)

    # -------------------------------------------------
    def _normalize(self, state):
        for k in state:
            val = state[k]
            if isinstance(val, (int, float)):
                state[k] = round(max(0, min(100, val)), 2)
        return state

    # -------------------------------------------------
    # 🔥 IMPROVED EVALUATION (CONTEXT-AWARE)
    # -------------------------------------------------
    def evaluate_state(self, state, context=None):

        cpu = self._get(state, "cpu")
        memory = self._get(state, "memory")
        disk = self._get(state, "disk")

        anomaly = self._get(context or {}, "anomaly_score")

        # 🔥 penalize anomaly heavily
        score = 100 - (cpu + memory + disk) - (anomaly * 10)

        return round(score, 3)

    # -------------------------------------------------
    def is_simulation_safe(self, before, after):

        cpu_jump = abs(after["cpu"] - self._get(before, "cpu"))
        memory_jump = abs(after["memory"] - self._get(before, "memory"))
        disk_jump = abs(after["disk"] - self._get(before, "disk"))

        if cpu_jump > self.MAX_CHANGE:
            return False, "cpu_jump_too_high"

        if memory_jump > self.MAX_CHANGE:
            return False, "memory_jump_too_high"

        if disk_jump > self.MAX_CHANGE:
            return False, "disk_jump_too_high"

        return True, "safe"

    # -------------------------------------------------
    # 🔥 BEST ACTION (UPGRADED)
    # -------------------------------------------------
    def find_best_action(self, state, actions, context=None):

        best_action = None
        best_score = float("-inf")

        results = []

        for action in actions:

            simulated = self.apply_action(state, action)

            safe, reason = self.is_simulation_safe(state, simulated)

            score = self.evaluate_state(simulated, context)

            confidence = self._estimate_confidence(state, simulated)

            explanation = self._explain_change(state, simulated)

            result = {
                "action": action,
                "score": score,
                "safe": safe,
                "reason": reason,
                "confidence": confidence,
                "impact": explanation,
                "state": simulated
            }

            results.append(result)

            if safe and score > best_score:
                best_score = score
                best_action = action

        return best_action, results

    # -------------------------------------------------
    def _estimate_confidence(self, before, after):

        change = (
            abs(after["cpu"] - self._get(before, "cpu")) +
            abs(after["memory"] - self._get(before, "memory")) +
            abs(after["disk"] - self._get(before, "disk"))
        )

        confidence = max(0.3, min(1.0, 1 - (change / 100)))

        return round(confidence, 3)

    # -------------------------------------------------
    # 🔥 EXPLAINABILITY (NEW)
    # -------------------------------------------------
    def _explain_change(self, before, after):

        return {
            "cpu_delta": round(after["cpu"] - self._get(before, "cpu"), 2),
            "memory_delta": round(after["memory"] - self._get(before, "memory"), 2),
            "disk_delta": round(after["disk"] - self._get(before, "disk"), 2),
        }

    # -------------------------------------------------
    # COUNTERFACTUAL
    # -------------------------------------------------
    def compare_actions(self, state, actions, context=None):

        comparison = {}

        for action in actions:
            simulated = self.apply_action(state, action)

            comparison[action] = {
                "score": self.evaluate_state(simulated, context),
                "confidence": self._estimate_confidence(state, simulated),
                "impact": self._explain_change(state, simulated)
            }

        return comparison
