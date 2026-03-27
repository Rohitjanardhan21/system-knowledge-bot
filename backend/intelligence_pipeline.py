import os
import json

from backend.decision_engine_v2 import DecisionEngineV2
from backend.action_executor import ActionExecutor
from backend.learning_engine import LearningEngine
from backend.timeline_engine import get_timeline

decision_engine = DecisionEngineV2()
executor = ActionExecutor()
learning_engine = LearningEngine()

CURRENT_FILE = "system_facts/current.json"
NODES_DIR = "system_facts/nodes"


# -----------------------------------------
# LOAD HELPERS
# -----------------------------------------
def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def load_nodes():
    nodes = []
    if os.path.exists(NODES_DIR):
        for f in os.listdir(NODES_DIR):
            try:
                with open(os.path.join(NODES_DIR, f)) as file:
                    nodes.append(json.load(file))
            except:
                continue
    return nodes


# -----------------------------------------
# 🔥 MAIN PIPELINE
# -----------------------------------------
def run_intelligence_pipeline():
    metrics = load_json(CURRENT_FILE)
    nodes = load_nodes()

    # -----------------------------------------
    # 🧠 LEARNING ENGINE (NEW)
    # -----------------------------------------
    learning_engine.update(metrics)

    thresholds = learning_engine.get_thresholds()
    learned_anomalies = learning_engine.detect_anomalies(metrics)
    patterns = learning_engine.detect_patterns()

    # -----------------------------------------
    # EXISTING SIGNALS
    # -----------------------------------------
    anomalies = metrics.get("anomalies", {})
    forecast = metrics.get("forecast", {})
    deviations = metrics.get("deviations", {})

    # 🔥 merge anomalies
    combined_anomalies = {
        "system": anomalies,
        "learned": learned_anomalies
    }

    # -----------------------------------------
    # 🧠 DECISION ENGINE (NOW ADAPTIVE)
    # -----------------------------------------
    decision = decision_engine.decide(
        metrics,
        combined_anomalies,
        forecast,
        deviations,
        nodes=nodes
    )

    # -----------------------------------------
    # ⚡ EXECUTION ENGINE
    # -----------------------------------------
    execution = None
    if decision.get("auto_execute") and decision.get("executable"):
        execution = executor.execute(decision)

    # -----------------------------------------
    # 📜 TIMELINE
    # -----------------------------------------
    timeline = get_timeline()

    # -----------------------------------------
    # 📦 FINAL RESPONSE (UI PAYLOAD)
    # -----------------------------------------
    return {
        "cpu": metrics.get("cpu", 0),
        "memory": metrics.get("memory", 0),
        "disk": metrics.get("disk", 0),

        "nodes": nodes,

        "processes": metrics.get("processes", []),
        "network": metrics.get("network", {}),
        "disk_io": metrics.get("disk_io", {}),

        "simulation": metrics.get("simulation", {}),

        "decision_data": decision,
        "execution": execution,

        # 🔥 NEW: LEARNING OUTPUT
        "learning": {
            "thresholds": thresholds,
            "patterns": patterns,
            "anomalies": learned_anomalies
        },

        # 🔥 TIMELINE
        "timeline": timeline
    }
