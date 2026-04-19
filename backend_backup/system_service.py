import json
from pathlib import Path

# import all your engines here
from backend.anomaly_engine import detect_anomalies
from backend.causal_graph_engine import build_causal_graph
from backend.decision_engine_v2 import decide_action
from backend.story_engine import SystemStoryEngine

FACT_FILE = Path("system_facts/current.json")


def get_system_summary():
    if not FACT_FILE.exists():
        return {"error": "No system data available"}

    data = json.loads(FACT_FILE.read_text())

    metrics = data.get("metrics", {})
    history = data.get("history", [])

    anomalies = detect_anomalies(metrics)
    causal_graph = build_causal_graph(history)
    decision = decide_action(metrics)

    story_engine = SystemStoryEngine()
    story = story_engine.generate(
        metrics,
        anomalies,
        causal_graph,
        decision,
        history=history
    )

    return {
        "metrics": metrics,
        "history": history,
        "anomalies": anomalies,
        "causal_graph": causal_graph,
        "decision_v2": decision,
        "system_story": story
    }
