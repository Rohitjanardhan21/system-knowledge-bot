import copy
import random


class SimulationEngine:

    # -------------------------------------------------
    # ✅ FIXED INIT (BACKWARD COMPATIBLE)
    # -------------------------------------------------
    def __init__(self, causal_graph=None):
        self.graph = causal_graph or {}

    # -----------------------------------------
    # APPLY ACTION (SAFE + CLEAN)
    # -----------------------------------------
    def apply_action(self, state, action):

        new_state = {
            "cpu": float(state.get("cpu", 0)),
            "memory": float(state.get("memory", 0)),
            "disk": float(state.get("disk", 0))
        }

        # -----------------------------------------
        # BASE EFFECTS
        # -----------------------------------------
        if action == "throttle_background_processes":
            new_state["cpu"] -= 20
            new_state["memory"] -= 5

        elif action == "free_memory_cache":
            new_state["memory"] -= 25

        elif action == "reduce_disk_io":
            new_state["disk"] -= 20

        elif action == "kill_high_cpu_process":
            new_state["cpu"] -= 35
            new_state["memory"] -= 10

        elif action == "preemptive_cpu_control":
            new_state["cpu"] -= 15

        # -----------------------------------------
        # 🔥 SAFE CAUSAL PROPAGATION
        # -----------------------------------------
        if isinstance(self.graph, dict):  # ✅ safety check
            for src, edges in self.graph.items():
                if src in new_state:
                    for tgt, weight in edges.items():
                        if tgt in new_state:
                            noise = random.uniform(0.8, 1.2)
                            impact = new_state[src] * weight * 0.05 * noise
                            new_state[tgt] += impact

        return self._normalize(new_state)

    # -----------------------------------------
    # SAFE NORMALIZATION
    # -----------------------------------------
    def _normalize(self, state):
        for k in state:
            val = state[k]

            if isinstance(val, (int, float)):
                state[k] = round(max(0, min(100, val)), 2)

        return state

    # -----------------------------------------
    # MULTI-STEP SIMULATION
    # -----------------------------------------
    def simulate_sequence(self, state, actions):

        timeline = []
        current = copy.deepcopy(state)

        for step, action in enumerate(actions):
            current = self.apply_action(current, action)

            timeline.append({
                "step": step + 1,
                "action": action,
                "state": current.copy()
            })

        return timeline

    # -----------------------------------------
    # EVALUATION FUNCTION
    # -----------------------------------------
    def evaluate_state(self, state, mode="balanced"):

        cpu = float(state.get("cpu", 0))
        memory = float(state.get("memory", 0))
        disk = float(state.get("disk", 0))

        if mode == "performance":
            return -(cpu * 1.5 + memory * 0.5 + disk * 0.3)

        elif mode == "stability":
            return -(cpu * 0.8 + memory * 1.5 + disk * 0.5)

        return -(cpu + memory + disk)

    # -----------------------------------------
    # ACTION COMPARISON
    # -----------------------------------------
    def find_best_action(self, state, actions, mode="balanced"):

        best_action = None
        best_score = float("-inf")

        results = []

        for action in actions:
            simulated = self.apply_action(state, action)
            score = self.evaluate_state(simulated, mode)

            results.append({
                "action": action,
                "score": round(score, 3),
                "result_state": simulated
            })

            if score > best_score:
                best_score = score
                best_action = action

        return best_action, results

    # -----------------------------------------
    # COUNTERFACTUAL ANALYSIS
    # -----------------------------------------
    def compare_actions(self, state, actions):

        comparison = {}

        for action in actions:
            simulated = self.apply_action(state, action)

            comparison[action] = {
                "cpu_change": simulated["cpu"] - state.get("cpu", 0),
                "memory_change": simulated["memory"] - state.get("memory", 0),
                "disk_change": simulated["disk"] - state.get("disk", 0)
            }

        return comparison
