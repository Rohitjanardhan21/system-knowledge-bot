import json
import platform
import socket
import time
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil
import requests


# --------------------------------------------------
# 🔧 CONFIG (FLEXIBLE)
# --------------------------------------------------
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000/node/update")
INTERVAL = float(os.getenv("COLLECT_INTERVAL", "2"))

ROOT_DIR = Path(__file__).resolve().parent
FACTS_DIR = ROOT_DIR / "system_facts"
NODES_DIR = FACTS_DIR / "nodes"
NODES_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# 🌐 SAFE IP DETECTION
# --------------------------------------------------
def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


# --------------------------------------------------
# 🔥 PROCESS NORMALIZATION (CRITICAL FIX)
# --------------------------------------------------
def normalize_name(name, cmd):
    name = (name or "").lower()
    cmd = " ".join(cmd or []).lower()

    # 🔥 unify all browsers
    if any(x in name or x in cmd for x in [
        "chrome", "chromium", "firefox", "brave", "edge"
    ]):
        return "browser"

    # 🔥 remove subprocess noise
    if "contentproc" in cmd:
        return "browser"

    return name


# --------------------------------------------------
# 🧠 PROCESS CLASSIFICATION
# --------------------------------------------------
def classify_process(name, cmd):
    name = (name or "").lower()
    cmd = " ".join(cmd or []).lower()

    if "browser" in name:
        return "browser"

    if "gnome" in name or "explorer" in name:
        return "system_ui"

    if any(x in name for x in ["python", "node", "java"]):
        return "development"

    if any(x in name for x in ["docker", "containerd"]):
        return "container"

    return "system"


# --------------------------------------------------
# 🔎 FILTER INVALID PROCESSES
# --------------------------------------------------
def is_valid_process(name, cpu):
    name = (name or "").lower()

    if not name:
        return False

    # OS noise
    if any(x in name for x in [
        "idle", "system idle", "systemd",
        "kworker", "[", "]"
    ]):
        return False

    # ignore tiny cpu
    if cpu < 0.5:
        return False

    return True


# --------------------------------------------------
# ⚙️ PROCESS COLLECTION
# --------------------------------------------------
def get_top_processes():

    processes = []
    node = platform.node()
    cpu_cores = psutil.cpu_count(logical=True) or 1

    # 🔥 prime CPU counters
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except:
            continue

    psutil.cpu_percent(interval=1)

    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            raw_name = p.info['name'] or "unknown"
            cmd = p.info.get("cmdline") or []

            cpu = p.cpu_percent(None) / cpu_cores
            mem = p.memory_percent()

            if not is_valid_process(raw_name, cpu):
                continue

            # 🔥 normalize
            name = normalize_name(raw_name, cmd)

            processes.append({
                "pid": p.info['pid'],
                "name": name,
                "cpu": round(cpu, 2),
                "memory": round(mem, 2),
                "node": node,
                "cmd": " ".join(cmd),
                "category": classify_process(name, cmd)
            })

        except:
            continue

    # 🔥 sort by CPU
    processes.sort(key=lambda x: x["cpu"], reverse=True)

    return processes[:10]


# --------------------------------------------------
# 📊 METRICS
# --------------------------------------------------
def get_metrics():

    cpu = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory().percent

    try:
        disk = psutil.disk_usage('/').percent
    except:
        disk = 0

    return {
        "cpu": cpu,
        "memory": memory,
        "disk": disk,
        "processes": get_top_processes()
    }


# --------------------------------------------------
# 💻 SYSTEM INFO
# --------------------------------------------------
def get_system_info():
    return {
        "hostname": socket.gethostname(),
        "ip": get_ip(),
        "os": platform.system(),
        "machine": platform.machine(),
        "cpu_cores": psutil.cpu_count()
    }


# --------------------------------------------------
# 📡 SEND DATA
# --------------------------------------------------
def send_to_server(payload):
    try:
        requests.post(SERVER_URL, json=payload, timeout=2)
    except Exception as e:
        print("❌ Send failed:", e)


# --------------------------------------------------
# 🚀 MAIN
# --------------------------------------------------
def main():

    node = platform.node()

    payload = {
        "node": node,
        "node_name": node,
        "system_info": get_system_info(),
        "metrics": get_metrics(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # save locally
    (NODES_DIR / f"{node}.json").write_text(json.dumps(payload, indent=2))

    # send to backend
    send_to_server(payload)

    # debug
    top = payload["metrics"]["processes"][0]["name"] if payload["metrics"]["processes"] else "None"

    print(f"✅ {node} | CPU: {payload['metrics']['cpu']}% | Top: {top}")


# --------------------------------------------------
# 🔁 LOOP MODE
# --------------------------------------------------
if __name__ == "__main__":

    print("🚀 System Collector Started")
    print(f"🌐 Server: {SERVER_URL}")
    print(f"⏱ Interval: {INTERVAL}s\n")

    while True:
        try:
            main()
        except Exception as e:
            print("❌ Collector error:", e)

        time.sleep(INTERVAL)
