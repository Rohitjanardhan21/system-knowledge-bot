# ---------------------------------------------------------
# 🧠 COGNITIVE MULTI AGENT SYSTEM (ZERO-HALLUCINATION SAFE)
# ---------------------------------------------------------

import numpy as np
from collections import deque
from datetime import datetime

from backend.dqn_agent import DQNAgent
from backend.simulation_engine import SimulationEngine
from backend.action_feedback import is_blocked
from backend.learning_engine import LearningEngine

from backend.multimodal_engine import process_multimodal
from backend.truth_engine import TruthEngine


# ---------------------------------------------------------
# 🧠 MEMORY ENGINE
# ---------------------------------------------------------
class MemoryEngine:
    def __init__(self, maxlen=200):
        self.history = deque(maxlen=maxlen)

    def update(self, state):
        self.history.append(state)

    def get_recent(self, n=10):
        return list(self.history)[-n:]

    def get_baseline(self):
        if not self.history:
            return 50
        return sum([h["cpu"] for h in self.history]) / len(self.history)


# ---------------------------------------------------------
# 🧠 CONFIDENCE CALIBRATION (CRITICAL)
# ---------------------------------------------------------
def calibrate_confidence(anomaly_score, stability, data_points):

    base = 0.5

    if anomaly_score > 1.5:
        base += 0.2

    if stability > 0.9:
        base += 0.2

    if data_points < 20:
        base -= 0.3

    return max(0.1, min(0.95, base))


# ---------------------------------------------------------
# 🧠 MULTI AGENT SYSTEM
# ---------------------------------------------------------
class MultiAgentSystem:

    def __init__(self):
        self.agent = DQNAgent()
        self.memory = MemoryEngine()
        self.simulator = SimulationEngine({})
        self.learning = LearningEngine()
        self.truth_engine = TruthEngine()

        self.decision_history = deque(maxlen=100)

    # -----------------------------------------------------
    # STATE BUILDER
    # -----------------------------------------------------
    def build_state(self, raw):
        processes = raw.get("process_ranking", [])
        root = processes[0] if processes else {}

        return {
            "cpu": float(raw.get("cpu", 0)),
            "memory": float(raw.get("memory", 0)),
            "disk": float(raw.get("disk", 0)),

            "temperature": float(raw.get("temp", 0)),
            "audio": raw.get("audio", []),
            "vibration": raw.get("vibration", []),

            "root_cause": root.get("name", "unknown"),
            "confidence": min(1.0, root.get("cpu", 0) / 100 + 0.5),
            "system_risk": float(raw.get("cpu", 0)) / 100,
        }

    # -----------------------------------------------------
    def derive_semantic(self, state):
        if state["cpu"] > 85:
            return {"system_state": "overloaded", "severity": "critical"}
        elif state["cpu"] > 65:
            return {"system_state": "elevated", "severity": "high"}
        return {"system_state": "normal", "severity": "low"}

    def infer_intent(self, state):
        if state["cpu"] > 75:
            return {"intent": "high_compute_task", "confidence": 0.85}
        return {"intent": "normal_usage", "confidence": 0.6}

    def build_context(self, raw):
        return {
            "system_type": raw.get("system_type", "generic"),
            "environment": raw.get("environment", "local"),
            "priority": "performance"
        }

    # -----------------------------------------------------
    def compute_metrics(self):
        history = self.memory.get_recent(10)

        if len(history) < 5:
            return {"trend": 0, "volatility": 0, "stability": 1}

        cpu_vals = [h["cpu"] for h in history]

        return {
            "trend": float(np.polyfit(range(len(cpu_vals)), cpu_vals, 1)[0]),
            "volatility": float(np.std(cpu_vals)),
            "stability": max(0, 1 - np.std(cpu_vals) / 50)
        }

    # -----------------------------------------------------
    def build_impact_chain(self, state):
        chain = []

        if state["cpu"] > 70:
            chain += ["high_cpu_load"]

        if state["memory"] > 80:
            chain += ["memory_pressure"]

        if state.get("physical_cause") == "mechanical_fault":
            chain += ["mechanical_instability"]

        if state.get("physical_cause") == "thermal_overload":
            chain += ["heat_buildup"]

        return chain

    # -----------------------------------------------------
    def get_action_space(self):
        return [
            "maintain_state",
            "reduce_compute_load",
            "optimize_memory_usage",
            "rebalance_resources",
            "investigate_physical_system",
        ]

    # -----------------------------------------------------
    def generate_events(self, state):
        events = []

        if state["cpu"] > 75:
            events.append("CPU spike")

        if state["stability"] < 0.7:
            events.append("System instability")

        if state["anomaly_score"] > 1.5:
            events.append("Physical anomaly detected")

        return events

    # -----------------------------------------------------
    def compute_reward(self, prev_state, new_state):
        reward = new_state.get("stability", 1) - prev_state.get("stability", 1)

        if new_state["cpu"] > 85:
            reward -= 0.2

        return reward

    # -----------------------------------------------------
    def should_auto_execute(self, decision):
        return (
            decision["confidence"] > 0.85 and
            decision["risk"] > 0.7 and
            decision["action"] != "maintain_state"
        )

    # -----------------------------------------------------
    def build_explanation(self, state):
        evidence = []

        if state["cpu"] > 80:
            evidence.append("High CPU usage")

        if state["anomaly_score"] > 1.5:
            evidence.append("Multi-modal anomaly detected")

        return evidence

    # -----------------------------------------------------
    def run(self, raw):

        state = self.build_state(raw)
        self.memory.update(state)

        state["baseline_cpu"] = self.memory.get_baseline()
        state.update(self.compute_metrics())

        semantic = self.derive_semantic(state)
        intent = self.infer_intent(state)
        context = self.build_context(raw)

        state.update(semantic)
        state.update(intent)

        # 🔥 MULTI-MODAL
        mm = process_multimodal(raw)
        state["anomaly_score"] = mm["anomaly_score"]
        state["physical_cause"] = mm["cause"]
        state["features"] = mm["features"]

        state["impact_chain"] = self.build_impact_chain(state)

        actions = [a for a in self.get_action_space() if not is_blocked(a)]
        rl_action = self.agent.select_action(state, actions)

        simulations = []

        for a in actions:
            try:
                s = self.simulator.apply_action(state, a)
                score = self.simulator.evaluate_state(s)
            except:
                score = 0

            simulations.append({"action": a, "score": score})

        simulations.sort(key=lambda x: x["score"], reverse=True)
        best_action = simulations[0]["action"]

        if state["anomaly_score"] > 1.5:
            best_action = "investigate_physical_system"

        # 🔥 CALIBRATED CONFIDENCE
        confidence = calibrate_confidence(
            state["anomaly_score"],
            state["stability"],
            len(self.memory.history)
        )

        decision = {
            "action": best_action,
            "confidence": confidence,
            "risk": state["system_risk"],
            "why": state["impact_chain"],
            "evidence": self.build_explanation(state),
            "physical_cause": state["physical_cause"]
        }

        decision["auto_execute"] = self.should_auto_execute(decision)

        # 🔥 TRUTH VALIDATION
        validation = self.truth_engine.validate(raw, state["features"], decision)

        # SAFETY OVERRIDE
        if not validation["valid"]:
            decision["action"] = "maintain_state"
            decision["confidence"] = 0.3
            decision["auto_execute"] = False

        # RL update
        try:
            next_state = self.simulator.apply_action(state, best_action)
            reward = self.compute_reward(state, next_state)
            self.agent.store_transition(state, best_action, reward, next_state)
            self.agent.train()
        except:
            pass

        self.decision_history.append({
            "time": datetime.utcnow().isoformat(),
            "action": decision["action"],
            "confidence": decision["confidence"]
        })

        return {
            "decision": decision,
            "validated": validation["valid"],
            "validation_issues": validation["issues"],
            "events": self.generate_events(state),
            "multimodal": mm,
            "prediction": {
                "trend": state["trend"],
                "stability": state["stability"]
            },
            "intelligence": {
                "stability": state["stability"],
                "score": confidence
            },
            "decision_history": list(self.decision_history)
        }

    # -----------------------------------------------------
    def autonomous_loop(self, raw):
        result = self.run(raw)

        if result["decision"]["auto_execute"]:
            try:
                self.simulator.apply_action(raw, result["decision"]["action"])
            except:
                pass

        return result
