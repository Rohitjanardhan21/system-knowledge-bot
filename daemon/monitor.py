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
from judgment.actions import recommend_actions
from judgment.action_validator import validate_actions
from judgment.posture import resolve_posture
from judgment.execution import build_execution_plan
from judgment.executor import execute_plan
from judgment.audit import record_execution
from state.state_writer import write_state

FACTS_PATH = PROJECT_ROOT / "system_facts" / "current.json"

# ----------------------------------------------------------
# NORMALIZATION — ABSOLUTE COMPATIBILITY
# ----------------------------------------------------------
def normalize_facts(raw: dict) -> dict:
    print("STEP 6: normalizing facts")

    source = raw.get("facts", raw)

    timestamp = (
        raw.get("collected_at")
        or source.get("metadata", {}).get("collected_at")
        or datetime.now(timezone.utc).isoformat()
    )

    # CPU
    cpu_info = source.get("cpu", {})
    cpu_usage = float(cpu_info.get("usage_percent", 0.0))
    cpu_cores = int(cpu_info.get("cores", 1))

    # Memory: collector reports bytes -> normalize to MB
    mem = source.get("memory", {})
    memory_used = float(mem.get("used", 0.0)) / (1024 ** 2)
    memory_total = float(mem.get("total", 0.0)) / (1024 ** 2)

    # Disk
    disk_used = 0.0
    for volume in source.get("storage", {}).get("volumes", []):
        mount = str(volume.get("mount", ""))
        if mount == "/" or mount.upper().startswith("C:"):
            disk_used = float(volume.get("percent", 0.0))
            break

    # Preserve collected system/application events.
    events = source.get("events", [])
    if not isinstance(events, list):
        events = []

    facts = {
        "timestamp": timestamp,

        "cpu": {
            "usage_percent": cpu_usage,
            "cores": cpu_cores,
        },

        "memory": {
            "used_mb": memory_used,
            "total_mb": memory_total,
        },

        "disk": {
            "used_percent": round(disk_used, 2),
        },

        "load": [0.0, 0.0, 0.0],

        "events": events,

        # Legacy compatibility
        "cpu_usage": cpu_usage,
        "cpu_cores": cpu_cores,
        "memory_used_mb": memory_used,
        "memory_total_mb": memory_total,
        "disk_used_percent": round(disk_used, 2),
    }

    print(
        f"  CPU: {cpu_usage:.1f}% | cores: {cpu_cores} | "
        f"RAM: {memory_used:.1f}/{memory_total:.1f} MB | "
        f"Disk: {disk_used:.1f}% | Events: {len(events)}"
    )

    print("STEP 7: normalization complete")
    return facts


def run_once():
    print("STEP 1: start")

    print("STEP 2: run collector")
    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "system_collectors" / "collect_system.py"),
        ],
        check=True,
    )
    print("STEP 3: collector done")

    print("STEP 4: load raw facts")
    if not FACTS_PATH.exists():
        raise RuntimeError("system_facts/current.json not found")

    with open(FACTS_PATH) as f:
        raw_facts = json.load(f)
    print("STEP 5: raw facts loaded")

    facts = normalize_facts(raw_facts)

    # Load historical telemetry for temporal reasoning.
    HISTORY_PATH = PROJECT_ROOT / "state" / "history.json"

    if HISTORY_PATH.exists():
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                history = json.load(f)

            if isinstance(history, list):
                facts["history"] = history
            else:
                facts["history"] = []

        except (json.JSONDecodeError, OSError):
            facts["history"] = []
    else:
        facts["history"] = []

    print("STEP 8: validate facts")
    validate_system_facts(facts)
    print("STEP 9: validation OK")

    print("STEP 10: reasoning")
    judgments = evaluate(facts, {})
    posture = resolve_posture(judgments)

    actions = recommend_actions(judgments, posture)
    actions = validate_actions(actions, posture)

    # Build a safety-gated execution plan.
    execution_plan = build_execution_plan(actions)

    # Execute only actions permitted by the safety gate.
    # The executor remains dry-run/simulation based.
    execution_results = execute_plan(execution_plan)

    # Persist every execution result for auditability.
    record_execution(execution_results)

    print("STEP 11: reasoning OK")
    print("STEP 11A: execution plan built")
    print("STEP 11B: execution completed")
    print("STEP 11C: audit persisted")

    print("STEP 12: write state")
    write_state(
        facts,
        judgments,
        posture,
        actions,
        execution_plan,
        execution_results,
    )

    print("STEP 13: state written")

    print("DONE — latest.json MUST exist now")


if __name__ == "__main__":
    run_once()
