# ---------------------------------------------------------
# 🧠 ROOT CAUSE ENGINE (ROBUST + INTEGRATED)
# ---------------------------------------------------------

import time
from collections import defaultdict


class RootCauseEngine:

    def __init__(self):
        self.history = defaultdict(list)

        self.category_weight = {
            "browser_active": 5,
            "development": 4,
            "container": 4,
            "browser_background": 2,
            "system_ui": 1,
            "system": 0
        }

    # ---------------------------------------------------------
    # 🔧 SAFE FLOAT
    # ---------------------------------------------------------
    def safe_float(self, val):
        try:
            return float(val)
        except:
            return 0.0

    # ---------------------------------------------------------
    # 🧠 SCORE PROCESS
    # ---------------------------------------------------------
    def score_process(self, p, total_cpu):

        name = p.get("name", "unknown")
        cpu = self.safe_float(p.get("cpu", 0))
        mem = self.safe_float(p.get("memory", 0))
        category = p.get("category", "system")

        # CPU contribution
        cpu_score = cpu

        # Dominance (safe)
        dominance = (cpu / max(total_cpu, 1)) * 100

        # Category weight
        category_score = self.category_weight.get(category, 0) * 10

        # Temporal persistence
        now = time.time()
        self.history[name].append((now, cpu))

        self.history[name] = [
            (t, c) for t, c in self.history[name]
            if now - t < 10
        ]

        persistence = len(self.history[name])

        # Final score (normalized)
        score = (
            cpu_score * 1.2 +
            dominance * 0.8 +
            category_score +
            persistence * 2 +
            mem * 0.3
        )

        return max(0, score)

    # ---------------------------------------------------------
    def get_severity(self, cpu):
        cpu = self.safe_float(cpu)

        if cpu > 85:
            return "CRITICAL"
        elif cpu > 70:
            return "HIGH"
        elif cpu > 50:
            return "MEDIUM"
        return "LOW"

    # ---------------------------------------------------------
    def analyze(self, nodes):

        if not nodes:
            return self._empty("no_data")

        all_processes = []
        total_cpu = 0.0

        # ---------------- COLLECT ----------------
        for node in nodes:

            metrics = node.get("metrics", {})
            node_cpu = self.safe_float(metrics.get("cpu", 0))
            total_cpu += node_cpu

            for p in metrics.get("processes", []):
                proc = {
                    "name": p.get("name", "unknown"),
                    "cpu": self.safe_float(p.get("cpu", 0)),
                    "memory": self.safe_float(p.get("memory", 0)),
                    "category": p.get("category", "system"),
                    "node": node.get("node") or node.get("node_name")
                }
                all_processes.append(proc)

        if not all_processes:
            return self._empty("no_processes")

        # ---------------- SCORE ----------------
        scored = []

        for p in all_processes:
            try:
                s = self.score_process(p, total_cpu)
                scored.append((s, p))
            except:
                continue

        if not scored:
            return self._empty("scoring_failed")

        scored.sort(reverse=True, key=lambda x: x[0])

        # ---------------- NORMALIZE CONFIDENCE ----------------
        max_score = max(scored[0][0], 1)

        top_k = scored[:3]
        root_causes = []

        for score, proc in top_k:
            confidence = round(score / max_score, 2)

            root_causes.append({
                "process": proc["name"],
                "node": proc["node"],
                "cpu": proc["cpu"],
                "memory": proc["memory"],
                "category": proc["category"],
                "confidence": confidence
            })

        primary = root_causes[0]

        explanation = (
            f"{primary['process']} is consuming {primary['cpu']}% CPU "
            f"on {primary.get('node')}, dominating system load."
        )

        return {
            "status": "ok",
            "primary": primary,
            "top_causes": root_causes,
            "severity": self.get_severity(primary["cpu"]),
            "confidence": primary["confidence"],
            "explanation": explanation,
            "total_processes": len(all_processes)
        }

    # ---------------------------------------------------------
    def _empty(self, status):
        return {
            "status": status,
            "primary": None,
            "top_causes": [],
            "severity": "LOW",
            "confidence": 0.0
        }


# ---------------------------------------------------------
# 🔥 SIMPLE FUNCTION WRAPPER (IMPORTANT)
# ---------------------------------------------------------
_engine = RootCauseEngine()


def rank_root_causes(state_or_nodes):
    """
    🔥 Universal interface

    Supports:
    - node-based input (cluster)
    - flat state input (fallback)
    """

    # Case 1: node-based
    if isinstance(state_or_nodes, list):
        return _engine.analyze(state_or_nodes)

    # Case 2: fallback (single system state)
    cpu = state_or_nodes.get("cpu", 0)
    mem = state_or_nodes.get("memory", 0)

    return {
        "status": "fallback",
        "primary": {
            "process": "system",
            "cpu": cpu,
            "memory": mem,
            "confidence": 0.5
        },
        "top_causes": [],
        "severity": _engine.get_severity(cpu),
        "confidence": 0.5
    }
