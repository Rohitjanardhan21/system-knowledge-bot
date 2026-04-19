# ---------------------------------------------------------
# 🧠 COGNITIVE MULTI AGENT SYSTEM (UNIFIED FINAL)
# ---------------------------------------------------------

import numpy as np
from collections import deque

# ---------------- OS SYSTEM ----------------
from backend.os_system.simulation_engine import SimulationEngine
from backend.os_system.action_feedback import is_blocked
from backend.os_system.root_cause_engine import rank_root_causes
from backend.os_system.system_logger import log_event
from backend.os_system.self_healing_engine import execute_action

# ---------------- CORE ----------------
from backend.core.learning_engine import LearningEngine
from backend.core.truth_engine import TruthEngine
from backend.core.fusion_engine import fuse_intelligence

# ---------------- VEHICLE ----------------
from backend.vehicle_system.multimodal_engine import process_multimodal
from backend.vehicle_system.failure_diagnosis import diagnose_failure

# ---------------- AGENT ----------------
from backend.dqn_agent import DQNAgent


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
# 🧠 HEALTH SCORE
# ---------------------------------------------------------
def compute_health_score(state):
    score = 100
    score -= state["cpu"] * 0.3
    score -= state["memory"] * 0.2
    score -= state["anomaly_score"] * 10
    return max(0, min(100, round(score)))


# ---------------------------------------------------------
# 🧠 CONFIDENCE CALIBRATION
# ---------------------------------------------------------
def calibrate_confidence(anomaly_score, stability, data_points):
    try:
        a_score = float(anomaly_score)
    except:
        a_score = 0.0

    base = 0.5

    if a_score > 1.5:
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
    # STATE BUILDER (OS + VEHICLE)
    # -----------------------------------------------------
    def build_state(self, raw):
        processes = raw.get("process_ranking", [])
        root = processes[0] if processes else {}

        return {
            # OS
            "cpu": float(raw.get("cpu", 0)),
            "memory": float(raw.get("memory", 0)),
            "disk": float(raw.get("disk", 0)),

            # Vehicle
            "temperature": float(raw.get("temp", raw.get("temperature", 0))),
            "audio": raw.get("audio", []),
            "vibration": raw.get("vibration", []),
            "speed": float(raw.get("speed", 0)),

            # Context
            "root_cause": root.get("name", "unknown"),
            "confidence": min(1.0, (root.get("cpu", 0) / 100) + 0.5),
            "system_risk": float(raw.get("cpu", 0)) / 100,
        }

    # -----------------------------------------------------
    # TEMPORAL METRICS
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
    # ACTION SPACE
    # -----------------------------------------------------
    def get_action_space(self):
        return [
            "maintain_state",
            "reduce_compute_load",
            "optimize_memory_usage",
            "investigate_physical_system",
            "emergency_brake",
            "safe_mode"
        ]

    # -----------------------------------------------------
    # EVENT GENERATION
    # -----------------------------------------------------
    def generate_events(self, state):
        events = []

        if state["cpu"] > 75:
            events.append({"message": "CPU spike", "severity": "HIGH"})

        if state.get("fusion", {}).get("confirmed_event"):
            events.append({"message": "Confirmed impact", "severity": "CRITICAL"})

        if state.get("diagnosis", {}).get("issue"):
            events.append({
                "message": state["diagnosis"]["issue"],
                "severity": state["diagnosis"].get("severity", "MEDIUM")
            })

        if state["anomaly_score"] > 3:
            events.append({"message": "Failsafe activated", "severity": "CRITICAL"})

        return events

    # -----------------------------------------------------
    # MAIN PIPELINE
    # -----------------------------------------------------
    def run(self, raw):

        # ---------------- STATE ----------------
        state = self.build_state(raw)
        self.memory.update(state)

        state["baseline_cpu"] = self.memory.get_baseline()
        state.update(self.compute_metrics())

        # ---------------- ROOT CAUSE ----------------
        state["root_causes"] = rank_root_causes(state)

        # ---------------- MULTIMODAL ----------------
        try:
            mm = process_multimodal(raw)
        except:
            mm = {
                "anomaly_score": 0,
                "vehicle_insight": {},
                "pre_impact": {},
                "features": {},
                "vision": {}
            }

        # SAFE anomaly extraction
        anomaly_raw = mm.get("anomaly_score", 0)
        if isinstance(anomaly_raw, dict):
            state["anomaly_score"] = float(anomaly_raw.get("score", 0))
        else:
            state["anomaly_score"] = float(anomaly_raw)

        # Signals
        state["signals"] = mm.get("vehicle_insight", {}).get("signals", {})
        state["hazard"] = mm.get("vehicle_insight", {}).get("hazard", {})
        state["pre_impact"] = mm.get("pre_impact", {})
        state["features"] = mm.get("features", {})
        state["vision"] = mm.get("vision", {})

        # ---------------- FUSION + DIAGNOSIS ----------------
        state["fusion"] = fuse_intelligence(state)
        state["diagnosis"] = diagnose_failure(state)

        # ---------------- HEALTH ----------------
        state["health_score"] = compute_health_score(state)

        # ---------------- ACTION SIMULATION ----------------
        actions = [a for a in self.get_action_space() if not is_blocked(a)]

        simulations = []
        for a in actions:
            try:
                s = self.simulator.apply_action(state, a)
                score = self.simulator.evaluate_state(s)
            except:
                score = 0

            simulations.append({"action": a, "score": score})

        simulations.sort(key=lambda x: x["score"], reverse=True)
        best_action = simulations[0]["action"] if simulations else "maintain_state"

        # ---------------- FAILSAFE ----------------
        if state["anomaly_score"] > 3:
            best_action = "safe_mode"

        # ---------------- DECISION ----------------
        confidence = calibrate_confidence(
            state["anomaly_score"],
            state["stability"],
            len(self.memory.history)
        )

        decision = {
            "action": best_action,
            "confidence": confidence,
            "risk": state["system_risk"],
            "fusion": state["fusion"],
            "diagnosis": state["diagnosis"]
        }

        decision["auto_execute"] = (
            decision["confidence"] > 0.85 and decision["action"] != "maintain_state"
        )

        # ---------------- SELF-HEALING ----------------
        execution = None
        if decision["auto_execute"]:
            execution = execute_action(decision["action"], state)

        # ---------------- LOGGING ----------------
        log_event({
            "decision": decision,
            "health": state["health_score"],
            "anomaly": state["anomaly_score"]
        })

        # ---------------- OUTPUT ----------------
        return {
            "decision": decision,
            "events": self.generate_events(state),
            "health_score": state["health_score"],
            "execution": execution,
            "root_causes": state["root_causes"],
            "simulations": simulations[:3],
            "learning": {
                "history_size": len(self.memory.history)
            },
            "intelligence": {
                "fusion": state["fusion"]
            },
            "anomaly_score": state["anomaly_score"]
        }

    # -----------------------------------------------------
    def autonomous_loop(self, raw):
        return self.run(raw)
