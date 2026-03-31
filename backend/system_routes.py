from fastapi import APIRouter
from pathlib import Path
import json
import time
import numpy as np
from statistics import mean

from backend.multi_agent_system import MultiAgentSystem
from backend.learning_engine import LearningEngine
from backend.self_healing_engine import SelfHealingEngine
from backend.multi_node_engine import MultiNodeEngine

# 🔥 NEW IMPORTS
from backend.pattern_engine import PatternEngine
from backend.multimodal_engine import process_multimodal


router = APIRouter()
NODES_DIR = Path("system_facts/nodes")

# ---------------------------------------------------------
# 🧠 CORE SYSTEMS
# ---------------------------------------------------------

agent_system = MultiAgentSystem()
learning_engine = LearningEngine()
self_healing_engine = SelfHealingEngine()
multi_node_engine = MultiNodeEngine()

# 🔥 NEW SYSTEMS
pattern_engine = PatternEngine()

# ---------------------------------------------------------
# 🔥 HISTORY (FOR ANOMALY BASELINE)
# ---------------------------------------------------------

HISTORY = {
    "cpu": [],
    "memory": []
}

WINDOW = 50


# ---------------------------------------------------------
# LOAD NODES
# ---------------------------------------------------------

def load_nodes():
    nodes = []

    if not NODES_DIR.exists():
        return nodes

    for f in NODES_DIR.glob("*.json"):
        try:
            nodes.append(json.loads(f.read_text()))
        except:
            continue

    return nodes


# ---------------------------------------------------------
# GLOBAL METRICS
# ---------------------------------------------------------

def compute_global(nodes):
    if not nodes:
        return {"cpu": 0, "memory": 0, "disk": 0}

    return {
        "cpu": round(mean([n.get("metrics", {}).get("cpu", 0) for n in nodes]), 2),
        "memory": round(mean([n.get("metrics", {}).get("memory", 0) for n in nodes]), 2),
        "disk": round(mean([n.get("metrics", {}).get("disk", 0) for n in nodes]), 2),
    }


# ---------------------------------------------------------
# PROCESS AGGREGATION
# ---------------------------------------------------------

def aggregate_processes(nodes):
    agg = {}

    for node in nodes:
        for p in node.get("metrics", {}).get("processes", []):
            name = p.get("name", "unknown").lower()

            if name not in agg:
                agg[name] = {
                    "name": name,
                    "cpu": 0,
                    "memory": 0
                }

            agg[name]["cpu"] += p.get("cpu", 0)
            agg[name]["memory"] += p.get("memory", 0)

    processes = list(agg.values())
    processes.sort(key=lambda x: x["cpu"], reverse=True)

    return processes


# ---------------------------------------------------------
# HISTORY
# ---------------------------------------------------------

def update_history(metric, value):
    HISTORY[metric].append(value)
    if len(HISTORY[metric]) > WINDOW:
        HISTORY[metric].pop(0)


def detect_anomaly(metric, value):
    data = HISTORY[metric]

    if len(data) < 10:
        return None

    arr = np.array(data)
    z = (value - arr.mean()) / (arr.std() + 1e-5)

    if abs(z) > 2.5:
        return {
            "metric": metric,
            "value": value,
            "z_score": round(float(z), 2)
        }

    return None


# ---------------------------------------------------------
# 🔥 MAIN SUMMARY (UNIFIED COGNITIVE BRAIN)
# ---------------------------------------------------------

@router.get("/summary")
def summary():

    # -----------------------------------------------------
    # 1. LOAD DATA
    # -----------------------------------------------------
    nodes = load_nodes()
    global_state = compute_global(nodes)
    processes = aggregate_processes(nodes)

    global_state["process_ranking"] = processes

    # -----------------------------------------------------
    # 2. HISTORY + BASIC ANOMALY
    # -----------------------------------------------------
    update_history("cpu", global_state["cpu"])
    update_history("memory", global_state["memory"])

    anomalies = []

    a1 = detect_anomaly("cpu", global_state["cpu"])
    a2 = detect_anomaly("memory", global_state["memory"])

    if a1: anomalies.append(a1)
    if a2: anomalies.append(a2)

    # -----------------------------------------------------
    # 3. 🧠 MULTI-MODAL INTELLIGENCE (NEW CORE)
    # -----------------------------------------------------
    multimodal = process_multimodal(global_state)

    features = multimodal.get("features", {})
    anomaly_score = multimodal.get("anomaly_score", 0)
    cause = multimodal.get("cause", "unknown")

    # -----------------------------------------------------
    # 4. 🧠 PATTERN ENGINE
    # -----------------------------------------------------
    pattern_output = pattern_engine.analyze(features)

    patterns = pattern_output.get("patterns", [])
    pattern_memory = pattern_output.get("pattern_memory", [])

    # -----------------------------------------------------
    # 5. 🧠 CORE AGENT SYSTEM
    # -----------------------------------------------------
    agent_result = agent_system.run(global_state)

    decision = agent_result.get("decision", {})
    analysis = agent_result.get("analysis", {})
    intelligence = agent_result.get("intelligence", {})
    events = agent_result.get("events", [])

    action = decision.get("action", "do_nothing")
    target = analysis.get("root_cause", "unknown")

    # -----------------------------------------------------
    # 🔥 ENHANCE DECISION WITH NEW INTELLIGENCE
    # -----------------------------------------------------
    decision["cause"] = cause
    decision["anomaly_score"] = anomaly_score

    if anomaly_score > 1.5:
        events.append("High anomaly score detected (multi-modal)")

    # -----------------------------------------------------
    # 6. 📚 LEARNING
    # -----------------------------------------------------
    learning = learning_engine.analyze(global_state) or {}
    learning["anomalies"] = anomalies

    # -----------------------------------------------------
    # 7. ⚡ SELF HEALING
    # -----------------------------------------------------
    auto_action = {
        "type": action,
        "target": target
    }

    execution = self_healing_engine.execute(auto_action) or {
        "status": "none"
    }

    # -----------------------------------------------------
    # 8. 🌐 CLUSTER ANALYSIS
    # -----------------------------------------------------
    cluster = multi_node_engine.analyze(nodes)

    # -----------------------------------------------------
    # 9. 🚀 FINAL RESPONSE
    # -----------------------------------------------------
    return {
        "cpu": global_state["cpu"],
        "memory": global_state["memory"],
        "disk": global_state["disk"],

        "process_ranking": processes[:10],

        # ------------------------------
        # 🧠 CORE INTELLIGENCE
        # ------------------------------
        "decision": decision,

        "root_cause": {
            "process": target,
            "inferred": cause
        },

        "intelligence": intelligence,

        # ------------------------------
        # 🔮 PREDICTION
        # ------------------------------
        "prediction": {
            "title": "trend",
            "details": str(intelligence.get("trend", 0))
        },

        # ------------------------------
        # ⚠️ RISK
        # ------------------------------
        "risk": {
            "level": decision.get("system_mode", "NORMAL"),
            "score": decision.get("confidence", 0)
        },

        # ------------------------------
        # ⚡ ACTION
        # ------------------------------
        "recommendation": {
            "message": decision.get("action", "do_nothing"),
            "actionable": decision.get("action") != "do_nothing",
            "auto_execute": decision.get("auto_execute", False)
        },

        # ------------------------------
        # 🧠 PATTERN INTELLIGENCE
        # ------------------------------
        "patterns": patterns,
        "pattern_memory": pattern_memory,

        # ------------------------------
        # 🔍 ANOMALY
        # ------------------------------
        "anomaly_score": anomaly_score,
        "anomalies": anomalies,

        # ------------------------------
        # 📡 EVENTS
        # ------------------------------
        "events": events,

        # ------------------------------
        # 📚 LEARNING
        # ------------------------------
        "learning": learning,

        # ------------------------------
        # ⚙️ EXECUTION
        # ------------------------------
        "execution": execution,

        # ------------------------------
        # 🌐 CLUSTER
        # ------------------------------
        "cluster": cluster,

        "timestamp": time.time()
    }


# ---------------------------------------------------------
# HELPER
# ---------------------------------------------------------

def get_system_summary():
    return summary()
