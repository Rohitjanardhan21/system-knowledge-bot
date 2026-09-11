from datetime import datetime, timezone

from backend.timeline_engine import log_event
from backend.policy_engine import PolicyEngine
from backend.dqn_agent import DQNAgent
from backend.os_system.simulation_engine import SimulationEngine
from backend.memory_engine import get_system_profile

# ✅ NEW IMPORT
from backend.core.causal_engine import CausalEngine
from backend.core.actions.action_executor import (
    ACTIONS,
    AUTONOMOUS_ALLOWED_ACTIONS,
)


class DecisionEngineV2:

    # Translate internal RL/policy actions into canonical executor actions.
    # Unmapped RL actions remain advisory and are never sent to the executor.
    RL_TO_EXECUTOR_ACTION = {
        "free_memory_cache": "drop_caches",
        "kill_high_cpu_process": "kill_high_cpu",
    }


    def __init__(self, agent=None):

        self.policy_engine = PolicyEngine()
        self.agent = agent if agent is not None else DQNAgent()

        self.simulator = SimulationEngine({
            "cpu": {"memory": 0.3, "disk": 0.2},
            "memory": {"cpu": 0.2},
            "disk": {"cpu": 0.25}
        })

        # ✅ NEW CAUSAL ENGINE
        self.causal_engine = CausalEngine()

        # -------------------------------------------------
        # COMPUTER CAUSAL → EXECUTOR TRANSLATION
        # -------------------------------------------------
        # CausalEngine uses domain-level recommendations.
        # ActionExecutor uses concrete action IDs.
        # Keep these vocabularies separate.
        self.causal_action_map = {
            "memory_pressure": {
                "action": "drop_caches",
                "mode": "remediation",
            },
            "disk_pressure": {
                "action": "clear_temp",
                "mode": "remediation",
            },
            "cpu_overload": {
                "action": "kill_high_cpu",
                "mode": "diagnostic",
            },
            "moderate_cpu_load": {
                "action": "kill_high_cpu",
                "mode": "diagnostic",
            },
        }

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
        application_attribution = metrics.get("application_attribution", [])

        # -------------------------------------------------
        # 🧠 CAUSAL ENGINE (UPDATED)
        # -------------------------------------------------
        learned_anomalies = anomalies.get("learned", []) if isinstance(anomalies, dict) else []

        # Convert learned anomaly magnitude into the scalar signal expected
        # by the causal engine. Keep the raw anomaly list intact downstream.
        anomaly_score = 0.0
        if learned_anomalies:
            anomaly_score = max(
                float(a.get("deviation", 0) or 0) / 100.0
                for a in learned_anomalies
                if isinstance(a, dict)
            )

        causal = self.causal_engine.detect(
            {
                "cpu_pct": cpu,
                "mem_pct": memory,
                "disk_pct": disk
            },
            {"cpu": {}, "memory": {}, "disk": {}},
            processes=processes,
            multimodal={"anomaly_score": anomaly_score}
        )

        primary_cause = causal.get("primary_cause", {})
        system_risk = causal.get("system_risk", 0)

        # Application-level attribution from the intelligence pipeline.
        if application_attribution:
            primary_cause["application_attribution"] = application_attribution

            # Preserve the node for downstream diagnosis.
            if "node" not in primary_cause:
                contributors = primary_cause.get("contributors", [])
                if contributors:
                    primary_cause["node"] = contributors[0].get("node", "unknown")
                else:
                    primary_cause["node"] = "unknown"

            dominant_app = application_attribution[0]
            contribution = float(
                dominant_app.get("contribution_percent", 0) or 0
            )

            if contribution > 60:
                impact = "dominant"
            elif contribution >= 30:
                impact = "significant"
            else:
                impact = "minor"

            primary_cause["primary_application"] = {
                "application": dominant_app.get("application"),
                "cpu": dominant_app.get("cpu", 0),
                "memory": dominant_app.get("memory", 0),
                "contribution_percent": contribution,
                "process_count": dominant_app.get("process_count", 0),
                "impact": impact,
            }

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
        causal_type = primary_cause.get("type")
        causal_recommendation = primary_cause.get(
            "recommended_action",
            "observe"
        )

        # Translate only computer-related causal recommendations
        # that have a real ActionExecutor equivalent.
        causal_mapping = self.causal_action_map.get(causal_type)
        mapped_causal_action = (
            causal_mapping.get("action")
            if causal_mapping
            else None
        )
        causal_action_mode = (
            causal_mapping.get("mode")
            if causal_mapping
            else "advisory"
        )

        if epsilon > 0.6:
            final_action = dqn_action
            reason = "[exploration] DQN exploring"
            confidence = 0.6

        elif system_risk > 0.7:
            # Simulation remains an advisory signal. Prefer a real
            # causal executor mapping when one exists; otherwise
            # retain the simulation action as a non-executable candidate.
            final_action = (
                mapped_causal_action
                if mapped_causal_action
                else best_action
            )
            reason = f"[{system_mode}] high risk → causal/simulation"
            confidence = 0.9

        elif system_risk > 0.4:
            # Prefer a real causal action when one exists.
            # Otherwise retain the causal recommendation as advisory
            # rather than inventing an executable action.
            final_action = (
                mapped_causal_action
                if mapped_causal_action
                else causal_recommendation
            )
            reason = f"[{system_mode}] causal decision"
            confidence = primary_cause.get("confidence", 0.7)

        else:
            final_action = dqn_action
            reason = f"[{system_mode}] stable → RL control"
            confidence = 0.8

        # -------------------------------------------------
        # POLICY ADVICE
        # -------------------------------------------------
        # Policy remains available for learning/decision context,
        # but cannot silently replace a causal action with an action
        # that has no ActionExecutor implementation.
        policy_action = (
            learned_action.get("action", dqn_action)
            if isinstance(learned_action, dict)
            else learned_action
        )

        if (
            learned_action
            and epsilon < 0.3
            and policy_action in AUTONOMOUS_ALLOWED_ACTIONS
        ):
            final_action = policy_action
            reason = "[policy] learned executable action"
            confidence = 0.9

        # -------------------------------------------------
        # 🛡️ CANONICAL ACTION GATE
        # -------------------------------------------------
        # DQN, simulation, and policy use internal action
        # vocabularies that are not necessarily executable.
        # Never expose one of those internal actions as the
        # final executable action.
        executable_action_ids = set(ACTIONS.keys())

        # Translate internal RL/policy actions into canonical executor actions
        # when a safe, explicit translation exists.
        translated_action = self.RL_TO_EXECUTOR_ACTION.get(final_action)
        if translated_action:
            final_action = translated_action
            reason = f"{reason} → RL executor translation"

        if final_action not in executable_action_ids:
            if mapped_causal_action:
                final_action = mapped_causal_action
                reason = f"{reason} → causal executor mapping"
            else:
                # Keep the causal recommendation as an explicit
                # advisory action rather than exposing an internal
                # RL/simulation action.
                final_action = causal_recommendation
                reason = f"{reason} → advisory recommendation"

        # -------------------------------------------------
        # 🔥 AUTO EXECUTION (SAFE)
        # -------------------------------------------------
        auto_execute = (
            system_risk > 0.4 or
            epsilon > 0.5 or
            system_mode == "high_performance"
        )

        # 🔴 SAFETY: NEVER AUTO-KILL PROCESSES
        if final_action in {"kill_process", "kill_high_cpu_process"}:
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
                "causal_type": causal_type,
                "causal_recommendation": causal_recommendation,
                "causal_action": mapped_causal_action,
                "causal_action_mode": causal_action_mode,
                "policy_action": policy_action,
                "caused_by": primary_cause.get("caused_by"),
                "impact_chain": primary_cause.get("impact_chain", []),
                "application_attribution": application_attribution
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

        autonomous_allowed = action in AUTONOMOUS_ALLOWED_ACTIONS
        executable = action in ACTIONS

        # Never claim autonomous execution for an action outside the
        # central autonomous allowlist.
        auto_execute = bool(auto_execute and autonomous_allowed)

        decision = {
            "decision": message,
            "action": action,
            "risk_level": risk,
            "confidence": confidence,
            "auto_execute": auto_execute,
            "requires_confirmation": not auto_execute,
            "executable": executable,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if extra:
            decision.update(extra)

        return decision

    # -------------------------------------------------
    def _log(self, event, decision):
        log_event({
            "time": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "action": decision.get("action"),
            "risk": decision.get("risk_level")
        })
