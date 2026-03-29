import os
import json
import platform
import socket
from datetime import datetime, timezone
from pathlib import Path

import psutil
import requests

# --------------------------------------------------
# PATHS
# --------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent

FACTS_DIR = ROOT_DIR / "system_facts"
HISTORY_DIR = FACTS_DIR / "history"
NODES_DIR = FACTS_DIR / "nodes"
CURRENT_PATH = FACTS_DIR / "current.json"

HISTORY_DIR.mkdir(parents=True, exist_ok=True)
NODES_DIR.mkdir(parents=True, exist_ok=True)

SERVER_URL = "http://127.0.0.1:8000/node/update"


# --------------------------------------------------
# SYSTEM INFO
# --------------------------------------------------

def get_system_info():
    return {
        "hostname": socket.gethostname(),
        "ip": socket.gethostbyname(socket.gethostname()),
        "os": platform.system(),
        "machine": platform.machine(),
        "cpu_cores": psutil.cpu_count(),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "boot_time": psutil.boot_time()
    }


# --------------------------------------------------
# METRICS
# --------------------------------------------------

def get_cpu():
    return psutil.cpu_percent(interval=0.3)


def get_memory():
    return psutil.virtual_memory().percent


def get_disk():
    try:
        return psutil.disk_usage('/').percent
    except:
        return 0


# --------------------------------------------------
# 🔥 PROCESS CLASSIFICATION
# --------------------------------------------------

def classify_process(name):
    name = (name or "").lower()

    if "chrome" in name:
        return "browser"
    if "code" in name or "python" in name:
        return "development"
    if "game" in name or "steam" in name:
        return "gaming"
    if "docker" in name:
        return "container"

    return "system"


# --------------------------------------------------
# 🔥 IMPROVED PROCESS TRACKING (CRITICAL FIX)
# --------------------------------------------------

def get_top_processes():

    processes = []

    # 🔥 Initialize CPU counters
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except:
            continue

    # 🔥 Allow CPU measurement window
    psutil.cpu_percent(interval=0.2)

    total_cpu = get_cpu()

    for p in psutil.process_iter(['pid', 'name']):
        try:
            cpu = p.cpu_percent(None)
            mem = p.memory_percent()

            # ignore noise
            if cpu < 1:
                continue

            name = p.info['name']

            processes.append({
                "pid": p.info['pid'],
                "name": name,
                "cpu": round(cpu, 2),
                "memory": round(mem, 2),

                # 🔥 NEW (for intelligence layer)
                "category": classify_process(name),
                "weight": round(cpu / max(total_cpu, 1), 2)
            })

        except:
            continue

    processes = sorted(processes, key=lambda x: x["cpu"], reverse=True)

    return processes[:5]


# --------------------------------------------------
# NETWORK
# --------------------------------------------------

def get_network():
    net = psutil.net_io_counters()
    return {
        "throughput_mb": round(net.bytes_sent / 1e6, 2)
    }


# --------------------------------------------------
# DISK IO
# --------------------------------------------------

def get_disk_io():
    io = psutil.disk_io_counters()
    return {
        "read_bytes": io.read_bytes,
        "write_bytes": io.write_bytes
    }


# --------------------------------------------------
# PUSH TO SERVER
# --------------------------------------------------

def send_to_server(data):
    try:
        requests.post(SERVER_URL, json=data, timeout=1)
    except:
        pass


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    NODE_ID = socket.gethostname()
    timestamp = datetime.now(timezone.utc).isoformat()

    system_info = get_system_info()

    cpu = get_cpu()
    memory = get_memory()
    disk = get_disk()

    processes = get_top_processes()

    metrics = {
        "cpu": cpu,
        "memory": memory,
        "disk": disk,
        "processes": processes,
        "network": get_network(),
        "disk_io": get_disk_io()
    }

    facts = {
        "node": NODE_ID,
        "system_info": system_info,
        "metrics": metrics,
        "tags": ["env:dev", "service:aiops"],
        "timestamp": timestamp
    }

    # SAVE FILE
    node_file = NODES_DIR / f"{NODE_ID}.json"
    node_file.write_text(json.dumps(facts, indent=2))

    # PUSH TO SERVER
    send_to_server(facts)

    print("✅ Data collected + sent")
    print(f"🔥 Top Process: {processes[0]['name'] if processes else 'None'}")


if __name__ == "__main__":
    main()
