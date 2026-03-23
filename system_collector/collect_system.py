import sys
from pathlib import Path

# --------------------------------------------------
# Ensure project root in PYTHONPATH
# --------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# --------------------------------------------------
# Standard imports
# --------------------------------------------------
import json
import os
import time
from datetime import datetime, timezone
import platform
import psutil

# Optional GPU support
try:
    import GPUtil
    GPU_AVAILABLE = True
except Exception:
    GPU_AVAILABLE = False

# --------------------------------------------------
# Project imports
# --------------------------------------------------
from system_collector.history_writer import write_snapshot
from judgment.engine import evaluate as evaluate_judgments
from judgment.posture import resolve_posture
from baseline.loader import load_baseline

# --------------------------------------------------
# Paths
# --------------------------------------------------
FACTS_DIR = "system_facts"
HISTORY_DIR = os.path.join(FACTS_DIR, "history")
CURRENT_PATH = os.path.join(FACTS_DIR, "current.json")

NETWORK_CACHE = os.path.join(FACTS_DIR, "network_cache.json")

COLLECTOR_VERSION = "1.0-os-agnostic"

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def safe_read_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def safe_write_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


# --------------------------------------------------
# Network Rate Calculation
# --------------------------------------------------

def get_network_rate():
    current = psutil.net_io_counters()

    now = time.time()

    prev = safe_read_json(NETWORK_CACHE, None)

    rate = {
        "bytes_sent_per_sec": 0,
        "bytes_recv_per_sec": 0,
    }

    if prev:
        dt = now - prev["timestamp"]
        if dt > 0:
            rate["bytes_sent_per_sec"] = (current.bytes_sent - prev["bytes_sent"]) / dt
            rate["bytes_recv_per_sec"] = (current.bytes_recv - prev["bytes_recv"]) / dt

    # store current
    safe_write_json(NETWORK_CACHE, {
        "bytes_sent": current.bytes_sent,
        "bytes_recv": current.bytes_recv,
        "timestamp": now
    })

    return {
        "total": {
            "bytes_sent": current.bytes_sent,
            "bytes_recv": current.bytes_recv,
            "packets_sent": current.packets_sent,
            "packets_recv": current.packets_recv,
        },
        "rate": rate
    }


# --------------------------------------------------
# Disk Collection (robust)
# --------------------------------------------------

def get_disk_metrics():
    disks = []

    for part in psutil.disk_partitions(all=False):
        try:
            # skip invalid / special mounts
            if not part.mountpoint:
                continue

            usage = psutil.disk_usage(part.mountpoint)

            disks.append({
                "device": part.device,
                "mount": part.mountpoint,
                "fstype": part.fstype,
                "percent": usage.percent,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
            })

        except PermissionError:
            continue
        except Exception:
            continue

    return disks


# --------------------------------------------------
# GPU Metrics (optional)
# --------------------------------------------------

def get_gpu_metrics():
    if not GPU_AVAILABLE:
        return {"status": "unavailable"}

    try:
        gpus = GPUtil.getGPUs()
        return [
            {
                "name": gpu.name,
                "load_percent": gpu.load * 100,
                "memory_used": gpu.memoryUsed,
                "memory_total": gpu.memoryTotal,
                "temperature": gpu.temperature,
            }
            for gpu in gpus
        ]
    except Exception:
        return {"status": "error"}


# --------------------------------------------------
# OS-Specific Enrichment (SAFE)
# --------------------------------------------------

def get_os_specific_metrics():
    system = platform.system()

    extra = {}

    try:
        if system == "Linux":
            extra["load_avg"] = os.getloadavg()

        elif system == "Windows":
            extra["process_count"] = len(psutil.pids())

        elif system == "Darwin":  # macOS
            extra["process_count"] = len(psutil.pids())

    except Exception:
        pass

    return extra


# --------------------------------------------------
# Core Metric Collection
# --------------------------------------------------

def collect_metrics():
    metrics = {}
    probes = {}

    # ---------- CPU ----------
    try:
        psutil.cpu_percent(interval=None)
        time.sleep(0.1)

        cpu_percent = psutil.cpu_percent(interval=0.5)
        per_core = psutil.cpu_percent(interval=0.5, percpu=True)

        metrics["cpu"] = {
            "usage_percent": cpu_percent,
            "per_core_percent": per_core,
            "core_count": psutil.cpu_count(),
            "max_core_usage": max(per_core) if per_core else 0,
        }

        probes["cpu"] = "ok"

    except Exception as e:
        metrics["cpu_error"] = str(e)
        probes["cpu"] = "fail"

    # ---------- MEMORY ----------
    try:
        vm = psutil.virtual_memory()

        metrics["memory"] = {
            "total": vm.total,
            "used": vm.used,
            "available": vm.available,
            "percent": vm.percent,
        }

        probes["memory"] = "ok"

    except Exception as e:
        metrics["memory_error"] = str(e)
        probes["memory"] = "fail"

    # ---------- DISK ----------
    try:
        metrics["disk"] = get_disk_metrics()
        probes["disk"] = "ok"
    except Exception as e:
        metrics["disk_error"] = str(e)
        probes["disk"] = "fail"

    # ---------- NETWORK ----------
    try:
        metrics["network"] = get_network_rate()
        probes["network"] = "ok"
    except Exception as e:
        metrics["network_error"] = str(e)
        probes["network"] = "fail"

    # ---------- GPU ----------
    metrics["gpu"] = get_gpu_metrics()
    probes["gpu"] = "ok" if GPU_AVAILABLE else "optional"

    # ---------- OS EXTRA ----------
    metrics["os_extra"] = get_os_specific_metrics()

    return metrics, probes


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    os.makedirs(HISTORY_DIR, exist_ok=True)

    started_at = time.time()

    metrics, probes = collect_metrics()

    facts = {
        "hostname": platform.node(),
        "os": platform.platform(),
        "metrics": metrics,
        "probes": probes,
    }

    collected_at = datetime.now(timezone.utc).isoformat()

    facts["metadata"] = {"collected_at": collected_at}

    facts["_meta"] = {
        "collector_version": COLLECTOR_VERSION,
        "runtime_seconds": round(time.time() - started_at, 3),
    }

    # ---------- inference ----------
    try:
        baseline = load_baseline()
    except Exception:
        baseline = {}

    try:
        judgments = evaluate_judgments(facts, baseline)
        posture_result = resolve_posture(judgments)

        facts["posture"] = {
            "posture": getattr(posture_result, "posture", None),
            "recommended_posture": getattr(posture_result, "recommended_posture", None),
            "explanation": getattr(posture_result, "explanation", None),
        }

    except Exception as e:
        facts["posture"] = {
            "posture": None,
            "recommended_posture": None,
            "explanation": f"inference_error: {str(e)}",
        }

    facts["posture_value"] = facts["posture"]["posture"]

    # ---------- history ----------
    safe_ts = collected_at.replace(":", "-")
    history_path = os.path.join(HISTORY_DIR, f"{safe_ts}.json")

    write_snapshot(history_path, facts)

    # ---------- current ----------
    with open(CURRENT_PATH, "w") as f:
        json.dump(facts, f, indent=2)

    print("✅ System facts collected (OS-agnostic).")


if __name__ == "__main__":
    main()
