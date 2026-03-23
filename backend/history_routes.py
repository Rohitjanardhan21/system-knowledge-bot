# backend/history_routes.py

from fastapi import APIRouter
from pathlib import Path
import json
from datetime import datetime

router = APIRouter(prefix="/history")

HISTORY_DIR = Path("system_facts/history")


@router.get("/query")
def query_history(from_ts: str, to_ts: str):

    start = datetime.fromisoformat(from_ts)
    end = datetime.fromisoformat(to_ts)

    out = []

    for f in HISTORY_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            ts = datetime.fromisoformat(d["timestamp"])
        except Exception:
            continue

        if start <= ts <= end:
            out.append({
                "ts": d["timestamp"],
                "cpu": d.get("metrics",{}).get("cpu_pct"),
                "memory": d.get("metrics",{}).get("mem_pct"),
                "posture": d.get("posture"),
                "bottleneck": d.get("bottleneck")
            })

    out.sort(key=lambda x: x["ts"])

    return out
