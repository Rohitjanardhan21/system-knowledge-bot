import numpy as np
from pathlib import Path
import json


HISTORY_DIR = Path("system_facts/history")


# ---------------------------------------------------------
# 🔹 SAFE CORRELATION (CRITICAL FIX)
# ---------------------------------------------------------
def safe_corr(x, y):
    try:
        if len(x) < 2 or len(y) < 2:
            return 0.0

        if np.std(x) == 0 or np.std(y) == 0:
            return 0.0

        corr = np.corrcoef(x, y)[0, 1]

        if np.isnan(corr):
            return 0.0

        return float(corr)

    except Exception:
        return 0.0


# ---------------------------------------------------------
# 🔹 LOAD HISTORY DATA
# ---------------------------------------------------------
def load_history(limit=50):
    data = []

    if not HISTORY_DIR.exists():
        return data

    files = sorted(HISTORY_DIR.glob("*.json"))[-limit:]

    for f in files:
        try:
            content = json.loads(f.read_text())
            metrics = content.get("metrics", {})

            data.append({
                "cpu": metrics.get("cpu", 0),
                "memory": metrics.get("memory", 0),
                "disk": metrics.get("disk", 0),
            })

        except Exception:
            continue

    return data


# ---------------------------------------------------------
# 🔥 CAUSAL GRAPH ENGINE
# ---------------------------------------------------------
class CausalGraph:

    def __init__(self):
        self.graph = {}
        self.explanations = []

    # -----------------------------------------------------
    # 🔹 BUILD GRAPH
    # -----------------------------------------------------
    def build_graph(self):
        history = load_history()

        if len(history) < 2:
            self.graph = {}
            return self.graph

        cpu_series = [h["cpu"] for h in history]
        mem_series = [h["memory"] for h in history]
        disk_series = [h["disk"] for h in history]

        # -------------------------------------------------
        # Compute correlations safely
        # -------------------------------------------------
        correlations = {
            ("cpu", "memory"): safe_corr(cpu_series, mem_series),
            ("cpu", "disk"): safe_corr(cpu_series, disk_series),
            ("memory", "disk"): safe_corr(mem_series, disk_series),
        }

        graph = {}

        for (a, b), corr in correlations.items():

            confidence = round(abs(corr), 2)

            if confidence < 0.1:
                continue  # ignore weak signals

            relation = {
                "correlation": round(corr, 2),
                "confidence": confidence
            }

            graph[f"{a}->{b}"] = relation
            graph[f"{b}->{a}"] = relation

            # explanation
            direction = "positive" if corr > 0 else "negative"

            self.explanations.append(
                f"{a} and {b} show a {direction} relationship (confidence {confidence})"
            )

        self.graph = graph
        return graph

    # -----------------------------------------------------
    # 🔹 GET EXPLANATIONS
    # -----------------------------------------------------
    def get_explanations(self):
        return self.explanations

    # -----------------------------------------------------
    # 🔹 ROOT CAUSE (VERY SIMPLE)
    # -----------------------------------------------------
    def find_root_cause(self, target="cpu"):
        causes = []

        for key, value in self.graph.items():
            src, dst = key.split("->")

            if dst == target:
                causes.append({
                    "metric": src,
                    "confidence": value["confidence"]
                })

        causes.sort(key=lambda x: x["confidence"], reverse=True)

        return causes
