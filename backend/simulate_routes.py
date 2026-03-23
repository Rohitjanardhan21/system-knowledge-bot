# backend/simulate_routes.py

from fastapi import APIRouter
import json
from pathlib import Path

router = APIRouter(prefix="/simulate")

FACTS = Path("system_facts/current.json")


@router.post("/workload")
def simulate_workload(payload: dict):

    if not FACTS.exists():
        return {"error": "no_telemetry"}

    facts = json.loads(FACTS.read_text())

    base_cpu = facts["metrics"]["cpu_pct"]
    base_mem = facts["metrics"]["mem_pct"]
    base_disk = facts["metrics"].get("disk_pct", 0)

    profile = payload.get("profile", "unknown")

    # conservative multipliers
    profiles = {
        "ml_training": (35, 25, 15),
        "docker_stack": (20, 15, 10),
        "video_render": (40, 20, 25),
        "database_load": (25, 10, 20),
        "build_job": (30, 8, 10),
    }

    d_cpu, d_mem, d_disk = profiles.get(profile, (10, 10, 5))

    new_cpu = min(100, base_cpu + d_cpu)
    new_mem = min(100, base_mem + d_mem)
    new_disk = min(100, base_disk + d_disk)

    posture = (
        "capacity-constrained"
        if max(new_cpu, new_mem, new_disk) > 90 else
        "performance-sensitive"
        if max(new_cpu, new_mem, new_disk) > 75 else
        "work-stable"
    )

    risk = max(new_cpu, new_mem, new_disk)

    return {
        "profile": profile,
        "predicted": {
            "cpu": new_cpu,
            "memory": new_mem,
            "disk": new_disk
        },
        "risk_score": risk,
        "likely_posture": posture,
        "confidence": 0.72,
        "notes": [
            "Simulation is heuristic",
            "Assumes sustained load for >10 minutes"
        ]
    }
