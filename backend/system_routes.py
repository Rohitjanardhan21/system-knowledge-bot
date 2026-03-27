from fastapi import APIRouter
from pathlib import Path
import json

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

# Detection
from backend.anomaly_engine import detect_anomalies
from backend.alert_engine import register_alerts
from backend.log_engine import log, get_logs

# Learning
from backend.cause_history import record as record_cause, get_top_causes

router = APIRouter()
NODES_DIR = Path("system_facts/nodes")

# ---------------------------------------------------------
# GLOBAL ENGINES
# ---------------------------------------------------------
dynamic_graph = DynamicCausalGraph()
causal_engine = CausalEngine()
temporal_engine = TemporalEngine()
predictor = PredictorEngine()
autonomous_engine = AutonomousEngine()


# ---------------------------------------------------------
# LOAD NODES
# ---------------------------------------------------------
def load_all_nodes():
    if not NODES_DIR.exists():
        return []

    nodes = []
    for file in NODES_DIR.glob("*.json"):
        try:
            nodes.append(json.loads(file.read_text()))
        except Exception as e:
            print("❌ Node read error:", e)

    return nodes


# ---------------------------------------------------------
# PROCESS NODE
# ---------------------------------------------------------
def process_node(node):
    metrics = node.get("metrics", {})

    return {
        "node_id": node.get("node"),
        "cpu": float(metrics.get("cpu", 0)),
        "memory": float(metrics.get("memory", 0)),
        "disk": float(metrics.get("disk", 0)),
        "processes": metrics.get("processes", [])
    }


# ---------------------------------------------------------
# AGGREGATE SYSTEM
# ---------------------------------------------------------
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
# PROCESS ACTIONS
# ---------------------------------------------------------
def get_process_actions(processes):

    actions = []

    for p in processes:
        cpu = p.get("cpu", 0)

        if cpu < 10:
            continue

        actions.append({
            "name": p.get("name"),
            "cpu": cpu,
            "target_pid": p.get("pid"),
            "target_name": p.get("name"),
            "actions": [
                {"type": "kill_process", "label": "Kill"},
                {"type": "throttle_process", "label": "Throttle"}
            ]
        })

    return sorted(actions, key=lambda x: x["cpu"], reverse=True)


# ---------------------------------------------------------
# BUILD SYSTEM STATE
# ---------------------------------------------------------
def build_system_state():

    raw_nodes = load_all_nodes()
    nodes = [process_node(n) for n in raw_nodes]
    global_state = aggregate(nodes)

    # -------- TEMPORAL --------
    temporal_engine.update(global_state)
    history = list(temporal_engine.history)
    temporal_patterns = temporal_analysis(history)

    # -------- PREDICTION --------
    prediction = predictor.predict(history, temporal_patterns)

    # -------- CAUSAL GRAPH --------
    dynamic_graph.update(global_state)
    dynamic_graph.compute_graph()
    graph = dynamic_graph.export()

    # -------- PROCESS LIST --------
    all_processes = []
    for n in nodes:
        all_processes.extend(n.get("processes", []))

    # -------- ANOMALIES --------
    node_anomalies = []
    for n in nodes:
        anomalies = detect_anomalies(n)
        if anomalies:
            node_anomalies.append({
                "node": n["node_id"],
                "anomalies": anomalies
            })

    global_anomalies = detect_anomalies(global_state)

    # -------- CAUSAL --------
    causal = causal_engine.detect(
        {
            "cpu_pct": global_state["cpu"],
            "mem_pct": global_state["memory"],
            "disk_pct": global_state["disk"]
        },
        temporal_patterns,
        learned_graph=graph,
        processes=all_processes
    )

    # -------- CAUSE HISTORY --------
    cause_type = causal.get("primary_cause", {}).get("type")
    record_cause(cause_type)

    return {
        "nodes": nodes,
        "global_state": global_state,
        "temporal": temporal_patterns,
        "prediction": prediction,
        "causal": causal,
        "graph": graph,
        "all_processes": all_processes,
        "node_anomalies": node_anomalies,
        "global_anomalies": global_anomalies
    }


# ---------------------------------------------------------
# MAIN SUMMARY
# ---------------------------------------------------------
def get_system_summary():

    state = build_system_state()

    nodes = state["nodes"]
    global_state = state["global_state"]

    # -------- PROCESS ACTIONS --------
    process_actions = get_process_actions(state["all_processes"])

    # -------- MAS --------
    mas = MultiAgentSystem()

    result = mas.run(
        global_state,
        nodes,
        context={
            "causal": state["causal"],
            "causal_graph": state["graph"]
        }
    )

    decision = result.get("decision", {}) or {}
    execution = result.get("execution") or {}

    # -------- AUTONOMOUS --------
    auto_decision = autonomous_engine.decide(
        state["prediction"],
        state["causal"],
        decision
    )

    executor = ActionExecutor()
    auto_execution = None

    if auto_decision and auto_decision.get("mode") == "auto":
        try:
            auto_execution = executor.execute({
                "action": auto_decision["action"],
                "executable": True,
                "auto": True
            })
        except Exception as e:
            auto_execution = {"error": str(e)}

    # -------- DIAGNOSIS --------
    diagnosis = generate_diagnosis(state)

    # -------- ALERTS + LOGS --------
    alerts = register_alerts(state["global_anomalies"])

    for a in state["global_anomalies"]:
        log(f"[GLOBAL] {a['type']}", level=a["severity"])

    # -------- FINAL RESPONSE --------
    return {
        "cpu": global_state["cpu"],
        "memory": global_state["memory"],
        "disk": global_state["disk"],
        "node_count": global_state["node_count"],

        "nodes": nodes,
        "process_actions": process_actions,

        "temporal": state["temporal"],
        "prediction": state["prediction"],
        "causal": state["causal"],
        "system_risk": state["causal"].get("system_risk", 0),

        "diagnosis": diagnosis,
        "top_causes": get_top_causes(),

        "decision_data": decision,
        "execution": execution,

        "autonomous_action": auto_decision,
        "autonomous_execution": auto_execution,

        "alerts": alerts,
        "logs": get_logs(),
        "timeline": get_timeline(),
    }


# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------
@router.get("/system/summary")
def system_summary():
    return get_system_summary()


@router.post("/system/execute")
def execute_action(decision: dict):
    executor = ActionExecutor()

    if not decision.get("executable"):
        return {"status": "blocked"}

    return executor.execute(decision)
