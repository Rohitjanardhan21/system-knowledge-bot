import os
import json
import platform
import socket
import uuid
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
# SYSTEM INFO (🔥 ENTERPRISE)
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
    return psutil.cpu_percent(interval=0.5)


def get_memory():
    return psutil.virtual_memory().percent


def get_disk():
    try:
        return psutil.disk_usage('/').percent
    except:
        return 0


def get_top_processes():
    processes = []

    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            processes.append({
                "pid": p.info['pid'],
                "name": p.info['name'],
                "cpu": p.info['cpu_percent'],
                "memory": round(p.info['memory_percent'], 2)
            })
        except:
            continue

    return sorted(processes, key=lambda x: x["cpu"], reverse=True)[:5]


def get_network():
    net = psutil.net_io_counters()
    return {
        "throughput": net.bytes_sent / 1e6
    }


def get_disk_io():
    io = psutil.disk_io_counters()
    return {
        "read": io.read_bytes,
        "write": io.write_bytes
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

    metrics = {
        "cpu": get_cpu(),
        "memory": get_memory(),
        "disk": get_disk(),
        "processes": get_top_processes(),
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

    # SAVE FILE (fallback)
    node_file = NODES_DIR / f"{NODE_ID}.json"
    node_file.write_text(json.dumps(facts, indent=2))

    # PUSH MODE (🔥 distributed)
    send_to_server(facts)

    print("✅ Data sent + saved")


if __name__ == "__main__":
    main()
