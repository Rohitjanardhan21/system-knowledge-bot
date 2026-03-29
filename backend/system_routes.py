from fastapi import APIRouter, Body
from pathlib import Path
import json
import time

# Core
from backend.timeline_engine import get_timeline
from backend.multi_agent_system import MultiAgentSystem
from backend.action_executor import ActionExecutor

# Intelligence
from backend.causal_engine import CausalEngine
from backend.dynamic_causal_graph import DynamicCausalGraph
from backend.temporal_engine import TemporalEngine, temporal_analysis
from backend.predictor_engine import PredictorEngine
from backend.autonomous_engine import AutonomousEngine
from backend.diagnosis_engine import generate_diagnosis

# New Intelligence Layers
from backend.context_engine import detect_context
from backend.baseline_engine import update as update_baseline, get_baseline

# Detection
from backend.anomaly_engine import detect_anomalies
from backend.alert_engine import register_alerts
from backend.log_engine import log, get_logs

# Learning
from backend.cause_history import record as record_cause, get_top_causes

# History
from backend.action_history import log_action, load_history

router = APIRouter()
NODES_DIR = Path("system_facts/nodes")

# GLOBAL
dynamic_graph = DynamicCausalGraph()
causal_engine = CausalEngine()
temporal_engine = TemporalEngine()
predictor = PredictorEngine()
autonomous_engine = AutonomousEngine()

# 🔥 duration tracker
issue_start_time = None


# ---------------------------------------------------------
# LOAD + PROCESS
# ---------------------------------------------------------
def load_all_nodes():
    if not NODES_DIR.exists():
        return []

    nodes = []
    for file in NODES_DIR.glob("*.json"):
        try:
            nodes.append(json.loads(file.read_text()))
        except Exception as e:
            print("Node error:", e)

    return nodes


def process_node(node):
    metrics = node.get("metrics", {})

    return {
        "node_id": node.get("node"),
        "cpu": float(metrics.get("cpu", 0)),
        "memory": float(metrics.get("memory", 0)),
        "disk": float(metrics.get("disk", 0)),
        "processes": metrics.get("processes", [])
    }


def aggregate(nodes):
    if not nodes:
        return {"cpu": 0, "memory": 0, "disk": 0, "node_count": 0}

    return {
        "cpu": sum(n["cpu"] for n in nodes) / len(nodes),
        "memory": sum(n["memory"] for n in nodes) / len(nodes),
        "disk": sum(n["disk"] for n in nodes) / len(nodes),
        "node_count": len(nodes)
    }


# ---------------------------------------------------------
# 🔥 DURATION TRACKING (NEW)
# ---------------------------------------------------------
def update_duration(cpu):
    global issue_start_time

    if cpu > 75:
        if issue_start_time is None:
            issue_start_time = time.time()
    else:
        issue_start_time = None

    if issue_start_time:
        return int(time.time() - issue_start_time)

    return 0


# ---------------------------------------------------------
# MAIN STATE
# ---------------------------------------------------------
def build_system_state():

    raw_nodes = load_all_nodes()
    nodes = [process_node(n) for n in raw_nodes]
    global_state = aggregate(nodes)

    duration = update_duration(global_state["cpu"])

    update_baseline(global_state["cpu"])
    baseline = get_baseline()

    temporal_engine.update(global_state)
    history = list(temporal_engine.history)
    temporal_patterns = temporal_analysis(history)

    prediction = predictor.predict(history, temporal_patterns)

    all_processes = []
    for n in nodes:
        all_processes.extend(n.get("processes", []))

    # 🔥 CONTEXT
    context = detect_context(all_processes)

    # 🔥 CAUSAL (with context + duration)
    causal = causal_engine.detect(
        {
            "cpu_pct": global_state["cpu"],
            "mem_pct": global_state["memory"],
            "disk_pct": global_state["disk"]
        },
        temporal_patterns,
        processes=all_processes,
        context=context,
        duration=duration
    )

    record_cause(causal.get("primary_cause", {}).get("type"))

    return {
        "nodes": nodes,
        "global_state": global_state,
        "prediction": prediction,
        "causal": causal,
        "all_processes": all_processes,
        "context": context,
        "baseline": baseline,
        "duration": duration
    }


# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------
def get_system_summary():

    state = build_system_state()

    global_state = state["global_state"]

    mas = MultiAgentSystem()

    decision = mas.run(
        global_state,
        state["nodes"],
        context={
            "context": state["context"],
            "causal": state["causal"]
        }
    ).get("decision", {})

    # 🔥 AUTONOMOUS (FULL CONTEXT)
    auto_decision = autonomous_engine.decide(
        state["prediction"],
        state["causal"],
        {
            **decision,
            "context": state["context"],
            "baseline_cpu": state["baseline"],
            "cpu": global_state["cpu"],
            "duration_seconds": state["duration"]
        }
    )

    diagnosis = generate_diagnosis(state)

    return {
        "cpu": global_state["cpu"],
        "memory": global_state["memory"],
        "disk": global_state["disk"],

        "context": state["context"],
        "duration_seconds": state["duration"],

        "prediction": state["prediction"],
        "causal": state["causal"],
        "system_risk": state["causal"].get("system_risk", 0),

        "diagnosis": diagnosis,
        "autonomous_action": auto_decision,

        "logs": get_logs(),
        "timeline": get_timeline(),
    }


# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------
@router.get("/system/summary")
def system_summary():
    return get_system_summary()


@router.post("/system/chat")
def system_chat(payload: dict = Body(...)):
    query = payload.get("message", "").lower()
    state = payload.get("state", {})

    action = state.get("autonomous_action")

    if "fix" in query:
        return {
            "answer": "I can fix this safely. Proceed?",
            "action": action,
            "requires_confirmation": True
        }

    return {"answer": state.get("diagnosis", {}).get("summary")}


@router.post("/system/execute")
def execute_action(payload: dict):
    executor = ActionExecutor()
    result = executor.execute(payload)
    log_action(payload, result)
    return result


@router.get("/system/history")
def get_history():
    return load_history()
