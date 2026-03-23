# backend/component_routes.py

from fastapi import APIRouter
import psutil
from datetime import datetime

router = APIRouter(prefix="/system/component")


@router.get("/{name}")
def component_details(name: str):

    out = {
        "component": name,
        "timestamp": datetime.utcnow().isoformat(),
        "forecast_weight": 0.0,
    }

    if name == "cpu":
        out["cores"] = psutil.cpu_percent(percpu=True)
        out["freq"] = psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {}
        out["top_processes"] = _top_cpu()

    elif name == "memory":
        vm = psutil.virtual_memory()
        out["memory"] = vm._asdict()
        out["top_processes"] = _top_mem()

    elif name == "disk":
        parts = psutil.disk_partitions()
        out["devices"] = [
            {
                "mount": p.mountpoint,
                "usage": psutil.disk_usage(p.mountpoint)._asdict()
            }
            for p in parts
        ]

    elif name == "network":
        io = psutil.net_io_counters(pernic=True)
        out["interfaces"] = {
            k: v._asdict() for k, v in io.items()
        }

    return out


def _top_cpu():
    procs = []
    for p in psutil.process_iter(["pid","name","cpu_percent"]):
        procs.append(p.info)
    return sorted(procs, key=lambda x: x["cpu_percent"] or 0, reverse=True)[:6]


def _top_mem():
    procs = []
    for p in psutil.process_iter(["pid","name","memory_percent"]):
        procs.append(p.info)
    return sorted(procs, key=lambda x: x["memory_percent"] or 0, reverse=True)[:6]
