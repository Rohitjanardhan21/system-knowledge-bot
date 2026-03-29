import copy
import random


class SimulationEngine:

    # -------------------------------------------------
    # INIT
    # -------------------------------------------------
    def __init__(self, causal_graph=None):
        self.graph = causal_graph or {}

        # 🔒 Safety limits
        self.MAX_CHANGE = 40  # max % change allowed per step
        self.NOISE_RANGE = (0.9, 1.1)

    # -------------------------------------------------
    # APPLY ACTION (SAFE + CONTROLLED)
    # -------------------------------------------------
    def apply_action(self, state, action):

        new_state = {
            "cpu": float(state.get("cpu", 0)),
            "memory": float(state.get("memory", 0)),
            "disk": float(state.get("disk", 0))
        }

        # -----------------------------------------
        # BASE EFFECTS (CAPPED)
        # -----------------------------------------
        def safe_delta(value):
            return max(-self.MAX_CHANGE, min(self.MAX_CHANGE, value))

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

        # -----------------------------------------
        # 🔥 SAFE CAUSAL PROPAGATION
        # -----------------------------------------
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
    # NORMALIZATION
    # -------------------------------------------------
    def _normalize(self, state):
        for k in state:
            val = state[k]
            if isinstance(val, (int, float)):
                state[k] = round(max(0, min(100, val)), 2)
        return state

    # -------------------------------------------------
    # MULTI-STEP SIMULATION
    # -------------------------------------------------
    def simulate_sequence(self, state, actions):

        timeline = []
        current = copy.deepcopy(state)

        for step, action in enumerate(actions):
            current = self.apply_action(current, action)

            timeline.append({
                "step": step + 1,
                "action": action,
                "state": current.copy(),
                "score": self.evaluate_state(current)
            })

        return timeline

    # -------------------------------------------------
    # EVALUATION FUNCTION (IMPROVED)
    # -------------------------------------------------
    def evaluate_state(self, state, mode="balanced"):

        cpu = float(state.get("cpu", 0))
        memory = float(state.get("memory", 0))
        disk = float(state.get("disk", 0))

        # lower is better → convert to positive score
        if mode == "performance":
            score = 100 - (cpu * 1.5 + memory * 0.5 + disk * 0.3)

        elif mode == "stability":
            score = 100 - (cpu * 0.8 + memory * 1.5 + disk * 0.5)

        else:
            score = 100 - (cpu + memory + disk)

        return round(score, 3)

    # -------------------------------------------------
    # 🔒 SAFETY CHECK (NEW)
    # -------------------------------------------------
    def is_simulation_safe(self, before, after):

        cpu_jump = abs(after["cpu"] - before.get("cpu", 0))
        memory_jump = abs(after["memory"] - before.get("memory", 0))
        disk_jump = abs(after["disk"] - before.get("disk", 0))

        # ❗ unrealistic jump → unsafe
        if cpu_jump > self.MAX_CHANGE:
            return False, "cpu_jump_too_high"

        if memory_jump > self.MAX_CHANGE:
            return False, "memory_jump_too_high"

        if disk_jump > self.MAX_CHANGE:
            return False, "disk_jump_too_high"

        return True, "safe"

    # -------------------------------------------------
    # 🔥 ACTION COMPARISON (UPGRADED)
    # -------------------------------------------------
    def find_best_action(self, state, actions, mode="balanced"):

        best_action = None
        best_score = float("-inf")

        results = []

        for action in actions:

            simulated = self.apply_action(state, action)

            # 🔒 Safety validation
            safe, reason = self.is_simulation_safe(state, simulated)

            score = self.evaluate_state(simulated, mode)

            confidence = self._estimate_confidence(state, simulated)

            results.append({
                "action": action,
                "score": score,
                "safe": safe,
                "safety_reason": reason,
                "confidence": confidence,
                "result_state": simulated
            })

            if safe and score > best_score:
                best_score = score
                best_action = action

        return best_action, results

    # -------------------------------------------------
    # 🔥 CONFIDENCE ESTIMATION (NEW)
    # -------------------------------------------------
    def _estimate_confidence(self, before, after):

        change = (
            abs(after["cpu"] - before.get("cpu", 0)) +
            abs(after["memory"] - before.get("memory", 0)) +
            abs(after["disk"] - before.get("disk", 0))
        )

        # smaller controlled change → higher confidence
        confidence = max(0.3, min(1.0, 1 - (change / 100)))

        return round(confidence, 3)

    # -------------------------------------------------
    # COUNTERFACTUAL ANALYSIS
    # -------------------------------------------------
    def compare_actions(self, state, actions):

        comparison = {}

        for action in actions:
            simulated = self.apply_action(state, action)

            comparison[action] = {
                "cpu_change": simulated["cpu"] - state.get("cpu", 0),
                "memory_change": simulated["memory"] - state.get("memory", 0),
                "disk_change": simulated["disk"] - state.get("disk", 0),
                "score": self.evaluate_state(simulated),
                "confidence": self._estimate_confidence(state, simulated)
            }

        return comparison
