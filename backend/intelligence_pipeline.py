from pathlib import Path
import os
import json
import time

from backend.decision_engine_v2 import DecisionEngineV2
from backend.action_executor import ActionExecutor
from backend.dqn_agent import DQNAgent
from backend.core.learning_engine import LearningEngine
from backend.timeline_engine import get_timeline

dqn_agent = DQNAgent()
decision_engine = DecisionEngineV2(agent=dqn_agent)
executor = ActionExecutor(agent=dqn_agent)
learning_engine = LearningEngine()

CURRENT_FILE = "system_facts/current.json"
NODES_DIR = "system_facts/nodes"
NODE_FRESHNESS_MAX_AGE_S = 120.0
NODE_MAX_FUTURE_SKEW_S = 30.0


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

    for file in Path(NODES_DIR).glob("*.json"):
        try:
            node = json.loads(file.read_text())

            if not isinstance(node, dict):
                continue

            if not node.get("node"):
                continue

            metrics = node.get("metrics", {})
            if not isinstance(metrics, dict):
                continue

            timestamp = node.get("timestamp")
            try:
                age = time.time() - float(timestamp)
            except (TypeError, ValueError):
                continue

            if age > NODE_FRESHNESS_MAX_AGE_S or age < -NODE_MAX_FUTURE_SKEW_S:
                continue

            if "processes" not in metrics:
                metrics["processes"] = []

            node["metrics"] = metrics
            nodes.append(node)

        except Exception:
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

        cpu = metrics.get(
            "cpu_percent",
            metrics.get("cpu_pct", metrics.get("cpu", 0))
        )
        memory = metrics.get(
            "memory",
            metrics.get("mem_pct", metrics.get("memory_percent", 0))
        )
        disk = metrics.get(
            "disk_percent",
            metrics.get("disk_pct", metrics.get("disk", 0))
        )

        try:
            cpu = float(cpu or 0)
        except (TypeError, ValueError):
            cpu = 0.0

        try:
            memory = float(memory or 0)
        except (TypeError, ValueError):
            memory = 0.0

        try:
            disk = float(disk or 0)
        except (TypeError, ValueError):
            disk = 0.0

        node_summary.append({
            "name": node_name,
            "cpu": cpu,
            "memory": memory,
            "disk": disk
        })

        for process in metrics.get("processes", []):
            p = dict(process)
            p["node"] = node_name
            if "memory" not in p and "mem" in p:
                p["memory"] = p["mem"]
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

    valid.sort(key=lambda x: x.get("cpu", 0), reverse=True)

    primary = valid[0]

    # Aggregate related processes into application/workload groups.
    # Prefer the existing category when available; otherwise use the
    # process name as a safe fallback.
    groups = {}

    for process in valid:
        application = process.get("application")
        category = process.get("category")
        name = process.get("name", "unknown")

        # Prefer explicit application identity when supplied by the
        # collector/agent. Fall back to category for older payloads.
        group = application or category or name
        group = str(group).strip().lower() or "unknown"

        if group not in groups:
            groups[group] = {
                "application": group,
                "cpu": 0.0,
                "memory": 0.0,
                "process_count": 0,
                "processes": [],
                "node": process.get("node", "unknown"),
            }

        groups[group]["cpu"] += float(process.get("cpu", 0) or 0)
        groups[group]["memory"] += float(
            process.get("memory", process.get("mem", 0)) or 0
        )
        groups[group]["process_count"] += 1
        groups[group]["processes"].append(process)

    total_cpu = sum(group["cpu"] for group in groups.values())

    attribution = []

    for group in groups.values():
        contribution = (
            (group["cpu"] / total_cpu) * 100
            if total_cpu > 0
            else 0.0
        )

        attribution.append({
            "application": group["application"],
            "cpu": round(group["cpu"], 2),
            "memory": round(group["memory"], 2),
            "contribution_percent": round(contribution, 2),
            "process_count": group["process_count"],
            "node": group["node"],
            "processes": group["processes"],
        })

    attribution.sort(
        key=lambda x: x["contribution_percent"],
        reverse=True
    )

    return {
        "process": primary["name"],
        "cpu": round(primary["cpu"], 2),
        "node": primary.get("node", "unknown"),
        "contributors": valid[:5],
        "application_attribution": attribution[:10],
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

    primary_app = root.get("primary_application")

    if primary_app:
        app_name = primary_app.get("application", "unknown")
        app_cpu = primary_app.get("cpu", 0)
        contribution = primary_app.get("contribution_percent", 0)
        process_count = primary_app.get("process_count", 0)
        impact = primary_app.get("impact", "unknown")

        summary = (
            f"{app_name} is the dominant application contributor, "
            f"using {app_cpu}% aggregate CPU across {process_count} processes "
            f"and accounting for {contribution}% of observed process CPU. "
            f"The primary process is {root['process']} at {root['cpu']}% CPU on "
            f"{root['node']}. Overall CPU is {cpu}% and memory usage is {memory}%."
        )

        return {
            "summary": summary,
            "primary_application": primary_app,
            "primary_process": {
                "name": root["process"],
                "cpu": root["cpu"],
                "node": root["node"]
            },
            "impact": impact
        }

    return {
        "summary": (
            f"{root.get('process', 'unknown')} is consuming {root.get('cpu', 0)}% CPU on {root.get('node', 'unknown')}. "
            f"This is the primary source of system load. "
            f"Overall CPU is {cpu}% and memory usage is {memory}%."
        )
    }

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

def run_intelligence_pipeline(allow_execution=True, live_metrics=None):

    raw_current = load_json(CURRENT_FILE)
    nodes = load_nodes()

    # Normalize current.json: telemetry is stored under "metrics".
    metrics = dict(raw_current.get("metrics", raw_current))

    # Preserve derived intelligence fields from current.json when present.
    for key in ("anomalies", "forecast", "deviations", "timestamp", "node", "hostname"):
        if key in raw_current:
            metrics[key] = raw_current[key]

    # Use live node telemetry as the authoritative system-level snapshot.
    # If no fresh nodes are available, fall back to the local live collector
    # rather than trusting stale system_facts/current.json telemetry.
    if live_metrics:
        metrics.update(live_metrics)
    elif nodes:
        _, live_node_summary = aggregate_nodes(nodes)
        if live_node_summary:
            metrics["cpu"] = sum(n["cpu"] for n in live_node_summary) / len(live_node_summary)
            metrics["memory"] = sum(n["memory"] for n in live_node_summary) / len(live_node_summary)
            metrics["disk"] = sum(n["disk"] for n in live_node_summary) / len(live_node_summary)
    else:
        local_live_metrics = executor.get_metrics()
        metrics.update(local_live_metrics)

    # -----------------------------------------
    # 🧠 LEARNING ENGINE
    # -----------------------------------------

    # Detect against the existing baseline BEFORE learning the new observation.
    # This prevents the current sample from diluting its own anomaly score.
    thresholds = learning_engine.get_baseline()
    learned_anomalies = learning_engine.detect_anomalies(metrics)

    # Learn the observation only after anomaly detection.
    learning_engine.update(metrics)

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
        {
            **metrics,
            "processes": all_processes,
            "application_attribution": (
                root.get("application_attribution", [])
                if root else []
            )
        },
        combined_anomalies,
        forecast=forecast,
        deviations=deviations,
        nodes=nodes
    )

    # -----------------------------------------
    # 🧠 SIMULATED DQN LEARNING
    # -----------------------------------------
    # Learn from a counterfactual transition without executing
    # any real remediation action.
    simulation_learning = executor.simulate_learning_step(metrics)

    # -----------------------------------------
    # ⚡ EXECUTION
    # -----------------------------------------

    execution = None
    if allow_execution and decision.get("auto_execute") and decision.get("executable"):
        execution = executor.execute(decision)

    # -----------------------------------------
    # 📜 TIMELINE
    # -----------------------------------------

    timeline = get_timeline()

    # -----------------------------------------
    # 📊 GLOBAL METRICS
    # -----------------------------------------

    if node_summary:
        avg_cpu = sum(n["cpu"] for n in node_summary) / len(node_summary)
        avg_memory = sum(n["memory"] for n in node_summary) / len(node_summary)
    else:
        avg_cpu = metrics.get("cpu", 0)
        avg_memory = metrics.get("memory", 0)

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
        "root_cause": root,

        "causal": {
            "primary_cause": root
        },

        # 🔥 APPLICATION / WORKLOAD ATTRIBUTION
        "application_attribution": (
            root.get("application_attribution", [])
            if root else []
        ),

        # 🔥 GLOBAL PROCESS
        "global_top_process": global_top,

        # 🔥 HUMAN INSIGHT
        "diagnosis": generate_diagnosis(
            decision.get("root_cause", root),
            avg_cpu,
            avg_memory
        ),

        # 🔥 PREDICTION
        "prediction": generate_prediction(all_processes),

        # 🔥 RISK
        # Causal/ML risk is authoritative because it is the same risk
        # used by DecisionEngineV2 for classification and action selection.
        "system_risk": decision.get("system_risk", 0),

        # 🔥 DECISION + EXECUTION
        "decision": decision,
        "decision_data": decision,
        "execution": execution,

        # 🔥 LEARNING
        "learning": {
            "thresholds": thresholds,
            "patterns": patterns,
            "anomalies": learned_anomalies,
            "simulation": simulation_learning
        },

        # 🔥 TIMELINE
        "timeline": timeline,

        # 🔥 RAW DEBUG (OPTIONAL)
        "network": metrics.get("network", {}),
        "disk_io": metrics.get("disk_io", {})
    }
