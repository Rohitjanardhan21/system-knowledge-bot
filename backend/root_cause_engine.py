import time
from collections import defaultdict


class RootCauseEngine:

    def __init__(self):
        self.history = defaultdict(list)

        # 🔥 CATEGORY PRIORITY
        self.category_weight = {
            "browser_active": 5,
            "development": 4,
            "container": 4,
            "browser_background": 2,
            "system_ui": 1,
            "system": 0
        }

    # ---------------------------------------------------------
    # 🧠 SCORE PROCESS (CORE LOGIC)
    # ---------------------------------------------------------
    def score_process(self, p, total_cpu):

        name = p.get("name", "unknown")
        cpu = float(p.get("cpu", 0))
        mem = float(p.get("memory", 0))
        category = p.get("category", "system")

        # ---------------- CPU IMPACT ----------------
        cpu_score = cpu

        # ---------------- DOMINANCE ----------------
        dominance = (cpu / max(total_cpu, 1)) * 100

        # ---------------- CATEGORY ----------------
        category_score = self.category_weight.get(category, 0) * 10

        # ---------------- TEMPORAL ----------------
        now = time.time()
        self.history[name].append((now, cpu))

        # keep last 10 sec
        self.history[name] = [
            (t, c) for t, c in self.history[name]
            if now - t < 10
        ]

        persistence = len(self.history[name])

        # ---------------- FINAL SCORE ----------------
        score = (
            cpu_score * 1.2 +
            dominance * 0.8 +
            category_score +
            persistence * 2 +
            mem * 0.3
        )

        return score

    # ---------------------------------------------------------
    # 🔥 ANALYZE ROOT CAUSE
    # ---------------------------------------------------------
    def analyze(self, nodes):

        if not nodes:
            return {}

        all_processes = []
        total_cpu = 0

        # ---------------- COLLECT DATA ----------------
        for node in nodes:

            metrics = node.get("metrics", {})

            node_cpu = metrics.get("cpu", 0)
            total_cpu += node_cpu

            for p in metrics.get("processes", []):
                p["node"] = node.get("node") or node.get("node_name")
                all_processes.append(p)

        if not all_processes:
            return {
                "status": "no_data",
                "message": "No processes available"
            }

        # ---------------- SCORE ALL ----------------
        scored = []

        for p in all_processes:
            try:
                s = self.score_process(p, total_cpu)
                scored.append((s, p))
            except:
                continue

        scored.sort(reverse=True, key=lambda x: x[0])

        root = scored[0][1]

        # ---------------- EXPLANATION ----------------
        explanation = (
            f"{root['name']} is consuming {root['cpu']}% CPU "
            f"on {root.get('node')}, contributing significantly to system load."
        )

        # ---------------- RETURN ----------------
        return {
            "node": root.get("node"),
            "process": root.get("name"),
            "cpu": root.get("cpu"),
            "memory": root.get("memory"),
            "category": root.get("category"),
            "confidence": round(min(1.0, scored[0][0] / 100), 2),
            "explanation": explanation
        }
