from datetime import datetime

from backend.timeline_engine import log_event
from backend.policy_engine import PolicyEngine
from backend.dqn_agent import DQNAgent
from backend.simulation_engine import SimulationEngine
from backend.memory_engine import get_system_profile

# ✅ NEW IMPORT
from backend.causal_engine import CausalEngine


class DecisionEngineV2:

    def __init__(self):

        self.policy_engine = PolicyEngine()
        self.agent = DQNAgent()

        self.simulator = SimulationEngine({
            "cpu": {"memory": 0.3, "disk": 0.2},
            "memory": {"cpu": 0.2},
            "disk": {"cpu": 0.25}
        })

        # ✅ NEW CAUSAL ENGINE
        self.causal_engine = CausalEngine()

    # -------------------------------------------------
    def decide(self, metrics, anomalies, **kwargs):

        cpu = metrics.get("cpu", 0)
        memory = metrics.get("memory", 0)
        disk = metrics.get("disk", 0)

        # -------------------------------------------------
        # 🧠 HARDWARE MODE
        # -------------------------------------------------
        profile = get_system_profile()

        ram = profile.get("memory", {}).get("total_gb", 8)
        gpu = profile.get("gpu", [])

        if ram > 16 and gpu:
            system_mode = "high_performance"
        elif ram > 8:
            system_mode = "balanced"
        else:
            system_mode = "lightweight"

        # -------------------------------------------------
        # 🧠 PROCESS EXTRACTION (IMPORTANT)
        # -------------------------------------------------
        processes = metrics.get("processes", [])

        # -------------------------------------------------
        # 🧠 CAUSAL ENGINE (UPDATED)
        # -------------------------------------------------
        causal = self.causal_engine.detect(
            {
                "cpu_pct": cpu,
                "mem_pct": memory,
                "disk_pct": disk
            },
            {"cpu": {}, "memory": {}, "disk": {}},
            processes=processes
        )

        primary_cause = causal.get("primary_cause", {})
        system_risk = causal.get("system_risk", 0)

        # -------------------------------------------------
        # 🤖 DQN
        # -------------------------------------------------
        state = self.agent.encode_state(metrics)
        dqn_action = self.agent.select_action(state)
        epsilon = self.agent.epsilon

        # -------------------------------------------------
        # 🔮 SIMULATION
        # -------------------------------------------------
        actions = [
            "kill_high_cpu_process",
            "throttle_background_processes",
            "free_memory_cache",
            "preemptive_cpu_control"
        ]

        try:
            best_action, simulations = self.simulator.find_best_action(metrics, actions)
        except Exception:
            best_action = dqn_action
            simulations = []

        # -------------------------------------------------
        # 🧠 POLICY
        # -------------------------------------------------
        learned_action = self.policy_engine.get_best_action(str(state))

        # -------------------------------------------------
        # 🔥 DECISION LOGIC
        # -------------------------------------------------
        if epsilon > 0.6:
            final_action = dqn_action
            reason = "[exploration] DQN exploring"
            confidence = 0.6

        elif system_risk > 0.7:
            final_action = best_action
            reason = f"[{system_mode}] high risk → simulation"
            confidence = 0.9

        elif system_risk > 0.4:
            final_action = primary_cause.get("recommended_action", dqn_action)
            reason = f"[{system_mode}] causal decision"
            confidence = primary_cause.get("confidence", 0.7)

        else:
            final_action = dqn_action
            reason = f"[{system_mode}] stable → RL control"
            confidence = 0.8

        # 🔥 POLICY OVERRIDE
        if learned_action and epsilon < 0.3:
            final_action = learned_action
            reason = "[policy] learned optimal"
            confidence = 0.9

        # -------------------------------------------------
        # 🔥 AUTO EXECUTION (SAFE)
        # -------------------------------------------------
        auto_execute = (
            system_risk > 0.4 or
            epsilon > 0.5 or
            system_mode == "high_performance"
        )

        # 🔴 SAFETY: NEVER AUTO-KILL PROCESSES
        if final_action == "kill_high_cpu_process":
            auto_execute = False

        # -------------------------------------------------
        # 🧠 BUILD DECISION
        # -------------------------------------------------
        decision = self._build_decision(
            reason,
            final_action,
            risk=self._risk_label(system_risk),
            confidence=round(confidence, 2),
            auto_execute=auto_execute,
            extra={
                "root_cause": primary_cause,
                "system_risk": system_risk,
                "simulations": simulations,
                "dqn_action": dqn_action,
                "system_mode": system_mode,
                "epsilon": epsilon,
                "caused_by": primary_cause.get("caused_by"),
                "impact_chain": primary_cause.get("impact_chain", [])
            }
        )

        self._log("Final decision", decision)

        return decision

    # -------------------------------------------------
    def _risk_label(self, r):
        if r > 0.7:
            return "HIGH"
        elif r > 0.4:
            return "MEDIUM"
        return "LOW"

    # -------------------------------------------------
    def _build_decision(self, message, action, risk, confidence, auto_execute, extra=None):

        decision = {
            "decision": message,
            "action": action,
            "risk_level": risk,
            "confidence": confidence,
            "auto_execute": auto_execute,
            "requires_confirmation": not auto_execute,
            "executable": True,
            "timestamp": datetime.utcnow().isoformat()
        }

        if extra:
            decision.update(extra)

        return decision

    # -------------------------------------------------
    def _log(self, event, decision):
        log_event({
            "time": datetime.utcnow().isoformat(),
            "event": event,
            "action": decision.get("action"),
            "risk": decision.get("risk_level")
        })
