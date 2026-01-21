# ==========================================================
# System Knowledge Bot — Phase 2 FINAL DEBUG VERSION
#
# Runs ONCE.
# Forces legacy + structured compatibility.
# Prints every step.
# ==========================================================

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

# ----------------------------------------------------------
# Project root
# ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# ----------------------------------------------------------
# Imports
# ----------------------------------------------------------
from contracts.validate_facts import validate_system_facts
from judgment.engine import evaluate
from judgment.posture import resolve_posture
from state.state_writer import write_state

FACTS_PATH = PROJECT_ROOT / "system_facts" / "current.json"

# ----------------------------------------------------------
# NORMALIZATION — ABSOLUTE COMPATIBILITY
# ----------------------------------------------------------
def normalize_facts(raw: dict) -> dict:
    print("STEP 6: normalizing facts")

    # ----- timestamp -----
    timestamp = raw.get("metadata", {}).get("collected_at")
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()

    # ----- CPU -----
    cpu_info = raw.get("cpu", {})
    cpu_usage = 0.0
    cpu_cores = cpu_info.get("logical_cores", 1)

    # ----- Memory -----
    mem = raw.get("memory", {})
    memory_used = mem.get("used_mb", 0.0)
    memory_total = mem.get("total_mb", 0.0)

    # ----- Disk -----
    used_percent = 0.0
    for fs in raw.get("storage", {}).get("filesystems", []):
        if fs.get("mount_point") == "/":
            size = fs.get("size_gb", 0)
            used = fs.get("used_gb", 0)
            if size > 0:
                used_percent = (used / size) * 100
            break

    disk_used = round(used_percent, 2)

    # ----- LOAD -----
    load = [0.0, 0.0, 0.0]

    # ----- FORCE ALL VIEWS -----
    facts = {
        # ===== CONTRACT STRUCTURE =====
        "timestamp": timestamp,
        "cpu": {
            "usage_percent": cpu_usage,
            "cores": cpu_cores
        },
        "memory": {
            "used_mb": memory_used,
            "total_mb": memory_total
        },
        "disk": {
            "used_percent": disk_used
        },
        "load": load,

        # ===== LEGACY FLAT KEYS =====
        "cpu_usage": cpu_usage,
        "cpu_cores": cpu_cores,
        "memory_used_mb": memory_used,
        "memory_total_mb": memory_total,
        "disk_used_percent": disk_used,
    }

    print("STEP 7: normalization complete")
    return facts


# ----------------------------------------------------------
# RUN ONCE
# ----------------------------------------------------------
def run_once():
    print("STEP 1: start")

    print("STEP 2: run collector")
    subprocess.run(
        ["python3", "system_collector/collect_system.py"],
        check=True
    )
    print("STEP 3: collector done")

    print("STEP 4: load raw facts")
    if not FACTS_PATH.exists():
        raise RuntimeError("system_facts/current.json not found")

    with open(FACTS_PATH) as f:
        raw_facts = json.load(f)
    print("STEP 5: raw facts loaded")

    facts = normalize_facts(raw_facts)

    print("STEP 8: validate facts")
    validate_system_facts(facts)
    print("STEP 9: validation OK")

    print("STEP 10: reasoning")
    judgments = evaluate(facts, {})
    posture = resolve_posture(judgments)
    print("STEP 11: reasoning OK")

    print("STEP 12: write state")
    write_state(facts, judgments, posture)
    print("STEP 13: state written")

    print("DONE — latest.json MUST exist now")


if __name__ == "__main__":
    run_once()
