from pathlib import Path
import json

NODES_DIR = Path("system_facts/nodes")


# ---------------------------------------------------------
# LOAD
# ---------------------------------------------------------
def load_all_nodes():
    nodes = []

    if not NODES_DIR.exists():
        return nodes

    for file in NODES_DIR.glob("*.json"):
        try:
            data = json.loads(file.read_text())
            nodes.append(data)
        except:
            continue

    return nodes


# ---------------------------------------------------------
# 🔥 PROCESS FILTER (CRITICAL)
# ---------------------------------------------------------
def is_valid_process(p):

    name = (p.get("name") or "").lower()

    if not name:
        return False

    if any(x in name for x in ["idle", "system idle"]):
        return False

    if p.get("cpu", 0) < 1:
        return False

    return True


# ---------------------------------------------------------
# 🔥 AGGREGATION
# ---------------------------------------------------------
def aggregate_metrics():

    nodes = load_all_nodes()

    if not nodes:
        return {
            "nodes": [],
            "global": {
                "cpu": 0,
                "memory": 0,
                "disk": 0,
                "top_process": None
            }
        }

    total_cpu = 0
    total_mem = 0
    total_disk = 0

    all_processes = []

    for node in nodes:

        metrics = node.get("metrics", {})

        cpu = metrics.get("cpu", 0)
        mem = metrics.get("memory", 0)
        disk = metrics.get("disk", 0)

        total_cpu += cpu
        total_mem += mem
        total_disk += disk

        node_name = node.get("node_name") or node.get("node") or "unknown"

        for p in metrics.get("processes", []):

            if not is_valid_process(p):
                continue

            all_processes.append({
                "name": p.get("name"),
                "cpu": p.get("cpu", 0),
                "memory": p.get("memory", 0),
                "node": node_name,
                "pid": p.get("pid")
            })

    # -----------------------------------------------------
    # 🔥 AVERAGE METRICS (FIXED)
    # -----------------------------------------------------
    count = len(nodes)

    avg_cpu = round(total_cpu / count, 2)
    avg_mem = round(total_mem / count, 2)
    avg_disk = round(total_disk / count, 2)

    # -----------------------------------------------------
    # 🔥 SAFE GLOBAL TOP PROCESS
    # -----------------------------------------------------
    if all_processes:
        all_processes.sort(key=lambda x: x.get("cpu", 0), reverse=True)
        top_process = all_processes[0]
    else:
        top_process = None

    # -----------------------------------------------------
    # 🔥 CLEAN NODE SUMMARY (UI READY)
    # -----------------------------------------------------
    node_summary = [
        {
            "name": n.get("node_name") or n.get("node"),
            "cpu": n.get("metrics", {}).get("cpu", 0),
            "memory": n.get("metrics", {}).get("memory", 0)
        }
        for n in nodes
    ]

    return {
        "nodes": node_summary,

        "global": {
            "cpu": avg_cpu,
            "memory": avg_mem,
            "disk": avg_disk,
            "top_process": top_process
        },

        # 🔥 optional but useful
        "processes": all_processes
    }
