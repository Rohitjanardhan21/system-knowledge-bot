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
# 🔥 AGGREGATION LAYER (CRITICAL)
# -----------------------------------------

def aggregate_nodes(nodes):

    all_processes = []
    node_summary = []

    for node in nodes:
        node_name = node.get("node_name") or node.get("node") or "unknown"
        metrics = node.get("metrics", {})

        cpu = metrics.get("cpu", 0)
        memory = metrics.get("memory", 0)

        node_summary.append({
            "name": node_name,
            "cpu": cpu,
            "memory": memory
        })

        for p in metrics.get("processes", []):
            p["node"] = node_name
            all_processes.append(p)

    return all_processes, node_summary


# -----------------------------------------
# 🔥 ROOT CAUSE ENGINE
# -----------------------------------------

def find_root_cause(processes):

    if not processes:
        return None

    valid = [p for p in processes if p.get("cpu", 0) > 1]

    if not valid:
        return None

    valid.sort(key=lambda x: x["cpu"], reverse=True)

    primary = valid[0]

    return {
        "process": primary["name"],
        "cpu": primary["cpu"],
        "node": primary.get("node", "unknown"),
        "contributors": valid[:5]
    }


# -----------------------------------------
# 🔥 GLOBAL PROCESS
# -----------------------------------------

def get_global_top(processes):
    if not processes:
        return None
    return sorted(processes, key=lambda x: x.get("cpu", 0), reverse=True)[0]


# -----------------------------------------
# 🔥 DIAGNOSIS (HUMAN READABLE)
# -----------------------------------------

def generate_diagnosis(root, cpu, memory):

    if not root:
        return {
            "summary": "System stable. No significant CPU load detected."
        }

    return {
        "summary": (
            f"{root['process']} is consuming {root['cpu']}% CPU on {root['node']}. "
            f"This is the primary source of system load. "
            f"Overall CPU is {cpu}% and memory usage is {memory}%."
        )
    }


# -----------------------------------------
# 🔥 PREDICTION
# -----------------------------------------

def generate_prediction(processes):

    if not processes:
        return {"type": "Stable", "confidence": 0.5}

    top_load = sum(p.get("cpu", 0) for p in processes[:3])

    if top_load > 70:
        return {"type": "CPU likely to increase", "confidence": 0.85}
    elif top_load > 40:
        return {"type": "Moderate load", "confidence": 0.7}

    return {"type": "Stable", "confidence": 0.6}


# -----------------------------------------
# 🔥 RISK SCORE
# -----------------------------------------

def compute_risk(cpu, memory):
    return min(1.0, (cpu * 0.6 + memory * 0.4) / 100)


# -----------------------------------------
# 🔥 MAIN PIPELINE
# -----------------------------------------

def run_intelligence_pipeline():

    metrics = load_json(CURRENT_FILE)
    nodes = load_nodes()

    # -----------------------------------------
    # 🧠 LEARNING ENGINE
    # -----------------------------------------

    learning_engine.update(metrics)

    thresholds = learning_engine.get_thresholds()
    learned_anomalies = learning_engine.detect_anomalies(metrics)
    patterns = learning_engine.detect_patterns()

    # -----------------------------------------
    # 🔥 AGGREGATION (NEW)
    # -----------------------------------------

    all_processes, node_summary = aggregate_nodes(nodes)

    root = find_root_cause(all_processes)
    global_top = get_global_top(all_processes)

    # -----------------------------------------
    # EXISTING SIGNALS
    # -----------------------------------------

    anomalies = metrics.get("anomalies", {})
    forecast = metrics.get("forecast", {})
    deviations = metrics.get("deviations", {})

    combined_anomalies = {
        "system": anomalies,
        "learned": learned_anomalies
    }

    # -----------------------------------------
    # 🧠 DECISION ENGINE
    # -----------------------------------------

    decision = decision_engine.decide(
        metrics,
        combined_anomalies,
        forecast,
        deviations,
        nodes=nodes
    )

    # -----------------------------------------
    # ⚡ EXECUTION
    # -----------------------------------------

    execution = None
    if decision.get("auto_execute") and decision.get("executable"):
        execution = executor.execute(decision)

    # -----------------------------------------
    # 📜 TIMELINE
    # -----------------------------------------

    timeline = get_timeline()

    # -----------------------------------------
    # 📊 GLOBAL METRICS
    # -----------------------------------------

    avg_cpu = sum(n["cpu"] for n in node_summary) / max(len(node_summary), 1)
    avg_memory = sum(n["memory"] for n in node_summary) / max(len(node_summary), 1)

    # -----------------------------------------
    # 📦 FINAL RESPONSE (UI READY)
    # -----------------------------------------

    return {
        # 🔥 CORE METRICS
        "cpu": round(avg_cpu, 2),
        "memory": round(avg_memory, 2),
        "disk": metrics.get("disk", 0),

        # 🔥 NODE VIEW (CLEAN)
        "nodes": node_summary,

        # 🔥 PROCESS VIEW
        "processes": sorted(all_processes, key=lambda x: x["cpu"], reverse=True)[:10],

        # 🔥 ROOT CAUSE
        "causal": {
            "primary_cause": root
        },

        # 🔥 GLOBAL PROCESS
        "global_top_process": global_top,

        # 🔥 HUMAN INSIGHT
        "diagnosis": generate_diagnosis(root, avg_cpu, avg_memory),

        # 🔥 PREDICTION
        "prediction": generate_prediction(all_processes),

        # 🔥 RISK
        "system_risk": compute_risk(avg_cpu, avg_memory),

        # 🔥 DECISION + EXECUTION
        "decision_data": decision,
        "execution": execution,

        # 🔥 LEARNING
        "learning": {
            "thresholds": thresholds,
            "patterns": patterns,
            "anomalies": learned_anomalies
        },

        # 🔥 TIMELINE
        "timeline": timeline,

        # 🔥 RAW DEBUG (OPTIONAL)
        "network": metrics.get("network", {}),
        "disk_io": metrics.get("disk_io", {})
    }
