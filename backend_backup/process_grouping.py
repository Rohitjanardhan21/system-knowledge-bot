import re
from collections import defaultdict


class ProcessGroupingEngine:

    def __init__(self):

        # 🔥 GROUP RULES
        self.rules = {
            "chrome": ["chrome", "chromium"],
            "firefox": ["firefox"],
            "docker": ["docker", "containerd"],
            "python": ["python"],
            "java": ["java"],
            "system_ui": ["gnome", "explorer"],
        }

    # ---------------------------------------------------------
    # 🔍 MATCH GROUP
    # ---------------------------------------------------------
    def get_group(self, name, cmd):

        name = (name or "").lower()
        cmd = (cmd or "").lower()

        for group, keywords in self.rules.items():
            if any(k in name or k in cmd for k in keywords):
                return group

        return "other"

    # ---------------------------------------------------------
    # 🔥 GROUP PROCESSES
    # ---------------------------------------------------------
    def group(self, processes):

        grouped = defaultdict(lambda: {
            "name": "",
            "cpu": 0,
            "memory": 0,
            "process_count": 0,
            "nodes": set(),
            "categories": set()
        })

        for p in processes:

            group_name = self.get_group(p.get("name"), p.get("cmd"))

            g = grouped[group_name]

            g["name"] = group_name
            g["cpu"] += p.get("cpu", 0)
            g["memory"] += p.get("memory", 0)
            g["process_count"] += 1
            g["nodes"].add(p.get("node"))
            g["categories"].add(p.get("category"))

        # 🔥 FINAL FORMAT
        result = []

        for g in grouped.values():
            result.append({
                "name": g["name"],
                "cpu": round(g["cpu"], 2),
                "memory": round(g["memory"], 2),
                "process_count": g["process_count"],
                "nodes": list(g["nodes"]),
                "category": list(g["categories"])[0] if g["categories"] else "system"
            })

        result.sort(key=lambda x: x["cpu"], reverse=True)

        return result
