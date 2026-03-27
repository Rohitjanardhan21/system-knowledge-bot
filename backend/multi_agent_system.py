# ---------------------------------------------------------
# 🧠 MULTI AGENT SYSTEM (SUPER INTELLIGENT VERSION)
# ---------------------------------------------------------

from backend.dqn_agent import DQNAgent
from backend.simulation_engine import SimulationEngine
from backend.action_executor import ActionExecutor

# 🔥 NEW
from backend.action_feedback import is_blocked


class MultiAgentSystem:

    def __init__(self):
        self.agent = DQNAgent()
        self.simulator = None
        self.executor = ActionExecutor()

    # -----------------------------------------------------
    # 🧠 BUILD STATE (ENRICHED)
    # -----------------------------------------------------
    def build_state(self, global_state, context=None):

        causal = (context or {}).get("causal", {})

        primary = causal.get("primary_cause", {}) or {}
        root_causes = causal.get("root_causes", []) or []

        return {
            "cpu": float(global_state.get("cpu", 0)),
            "memory": float(global_state.get("memory", 0)),
            "disk": float(global_state.get("disk", 0)),

            "root_cause": primary.get("type", "unknown"),
            "confidence": float(primary.get("confidence", 0)),
            "severity": float(primary.get("severity", 0)),
            "system_risk": float(causal.get("system_risk", 0)),

            "impact_chain": primary.get("impact_chain", []),
            "num_root_causes": len(root_causes),

            # 🔥 NEW
            "context": (context or {}).get("context", "general"),
            "baseline_cpu": (context or {}).get("baseline_cpu", 50),
        }

    # -----------------------------------------------------
    def get_action_space(self):
        return [
            "do_nothing",
            "kill_high_cpu_process",
            "free_memory_cache",
            "reduce_disk_io",
            "throttle_background_processes",
            "scale_resources",
        ]

    # -----------------------------------------------------
    def prioritize_actions(self, state):

        cause = state.get("root_cause")

        mapping = {
            "cpu_overload": ["throttle_background_processes", "kill_high_cpu_process"],
            "memory_pressure": ["free_memory_cache"],
            "disk_io_bottleneck": ["reduce_disk_io"],
            "latency_spike": ["scale_resources"],
        }

        return mapping.get(cause, self.get_action_space())

    # -----------------------------------------------------
    # 🧠 RUN SYSTEM
    # -----------------------------------------------------
    def run(self, global_state, nodes, context=None):

        # -------------------------------------------------
        # 🧠 BUILD STATE
        # -------------------------------------------------
        state = self.build_state(global_state, context)

        learned_graph = (context or {}).get("causal_graph", {}) or {}

        self.simulator = SimulationEngine(learned_graph)

        # -------------------------------------------------
        # 🔥 CONTEXT-AWARE FILTERING
        # -------------------------------------------------
        user_context = state.get("context")

        if user_context == "gaming":
            # 🚫 never interfere with gaming
            return self._safe_response(state, "User is gaming")

        # -------------------------------------------------
        # 🔥 BASELINE-AWARE FILTERING
        # -------------------------------------------------
        baseline = state.get("baseline_cpu", 50)

        if state["cpu"] < baseline + 20:
            return self._safe_response(state, "Within normal usage")

        # -------------------------------------------------
        # ACTION SPACE
        # -------------------------------------------------
        actions = self.get_action_space()

        # 🔥 REMOVE BAD ACTIONS
        actions = [a for a in actions if not is_blocked(a)]

        prioritized = self.prioritize_actions(state)

        # -------------------------------------------------
        # 🤖 RL DECISION (SAFE INPUT)
        # -------------------------------------------------
        safe_state = {
            "cpu": state["cpu"],
            "memory": state["memory"],
            "disk": state["disk"],
            "risk": state["system_risk"],
            "confidence": state["confidence"],
        }

        action = self.agent.select_action(safe_state, actions)

        # -------------------------------------------------
        # 🔥 SIMULATION (ROBUST)
        # -------------------------------------------------
        simulations = []

        for a in prioritized:
            try:
                simulated = self.simulator.apply_action(state, a)
                score = self.simulator.evaluate_state(simulated)
            except Exception:
                simulated = {}
                score = 0

            simulations.append({
                "action": a,
                "score": score,
                "result_state": simulated
            })

        simulations.sort(key=lambda x: x["score"], reverse=True)
        best_sim = simulations[0] if simulations else {}

        # -------------------------------------------------
        # 🔥 SAFETY FILTER
        # -------------------------------------------------
        best_action = best_sim.get("action", action)

        if best_action == "kill_high_cpu_process":
            # never auto execute kill
            auto_execute = False
        else:
            auto_execute = (
                state["system_risk"] > 0.8 or
                (state["confidence"] > 0.85 and state["severity"] > 0.7)
            )

        # -------------------------------------------------
        # FINAL DECISION
        # -------------------------------------------------
        decision = {
            "decision": f"Respond to {state['root_cause']}",
            "action": best_action,
            "confidence": state["confidence"],
            "risk": state["system_risk"],
            "auto_execute": auto_execute,
            "simulations": simulations,
            "system_mode": self.get_system_mode(state),
            "state": state
        }

        execution = {
            "status": "pending",
            "epsilon": getattr(self.agent, "epsilon", 0),
            "optimizer": {
                "reward_scale": best_sim.get("score", 0)
            }
        }

        analysis = {
            "root_cause": state["root_cause"],
            "risk": state["system_risk"],
            "impact_chain": state["impact_chain"],
            "context": user_context
        }

        return {
            "decision": decision,
            "execution": execution,
            "analysis": analysis
        }

    # -----------------------------------------------------
    # SAFE FALLBACK RESPONSE
    # -----------------------------------------------------
    def _safe_response(self, state, reason):

        return {
            "decision": {
                "decision": f"No action ({reason})",
                "action": "do_nothing",
                "confidence": state["confidence"],
                "risk": state["system_risk"],
                "auto_execute": False,
                "simulations": [],
                "system_mode": self.get_system_mode(state),
                "state": state
            },
            "execution": {
                "status": "skipped",
                "reason": reason
            },
            "analysis": {
                "root_cause": state["root_cause"],
                "context": state.get("context")
            }
        }

    # -----------------------------------------------------
    def get_system_mode(self, state):

        risk = state.get("system_risk", 0)

        if risk > 0.85:
            return "critical"
        elif risk > 0.6:
            return "stressed"
        elif risk > 0.3:
            return "elevated"
        else:
            return "stable"
