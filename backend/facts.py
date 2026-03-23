import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACTS_PATH = os.path.join(BASE_DIR, "..", "system_facts", "current.json")

TTL_SECONDS = 300


def load_facts():
    if not os.path.exists(FACTS_PATH):
        return {}
    with open(FACTS_PATH) as f:
        return json.load(f)


@router.get("/system/health")
def system_health():

    facts = load_facts()

    if not facts:
        return {
            "overall_health": "error",
            "facts_age_seconds": None,
            "ttl_seconds": TTL_SECONDS,
            "probes": {},
            "posture": None,
        }

    meta = facts.get("metadata", {})
    ts_raw = meta.get("collected_at")

    age = None
    if ts_raw:
        ts = datetime.fromisoformat(ts_raw)
        age = (datetime.now(timezone.utc) - ts).total_seconds()

    posture_block = facts.get("posture") or {}

    return {
        "posture": posture_block,
        "facts_age_seconds": age,
        "ttl_seconds": TTL_SECONDS,
        "collector_last_run": ts_raw,
        "overall_health": "stale" if age and age > TTL_SECONDS else "ok",
        "probes": facts.get("probes", {}),
    }
