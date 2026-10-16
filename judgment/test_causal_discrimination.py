from __future__ import annotations

import json
import uuid

from backend.intelligence_pipeline import run_intelligence_pipeline


def extract(result):
    decision = result.get("decision") or {}
    root = decision.get("root_cause") or result.get("root_cause") or {}
    causal = result.get("causal") or {}

    if not isinstance(root, dict):
        root = {}

    if not isinstance(causal, dict):
        causal = {}

    primary = causal.get("primary_cause")

    if isinstance(primary, dict):
        primary_type = primary.get("type")
        primary_process = primary.get("process")
    else:
        primary_type = primary
        primary_process = None

    return {
        "root_cause_type": root.get("type"),
        "causal_primary": primary,
        "causal_primary_type": primary_type,
        "causal_primary_process": primary_process,
        "causal_type": result.get("causal_type"),
        "causal_recommendation": result.get("causal_recommendation"),
        "causal_action": result.get("causal_action"),
        "action": decision.get("action"),
        "auto_execute": decision.get("auto_execute"),
        "requires_confirmation": decision.get("requires_confirmation"),
        "process": root.get("process"),
        "cpu": result.get("cpu"),
        "memory": result.get("memory"),
    }


def run_case(name, cpu, memory, process_cpu, expected_root_types):
    print()
    print("=" * 80)
    print(f"CASE: {name}")
    print("=" * 80)

    pid = 70000 + (uuid.uuid4().int % 10000)

    live_metrics = {
        "cpu_percent": float(cpu),
        "memory_percent": float(memory),
        "disk_percent": 40.0,
        "anomaly_score": 0.95,

        "process_id": pid,
        "process_name": "controlled-test-process.exe",
        "process_cpu_percent": float(process_cpu),
        "process_memory_percent": float(memory / 4.0),

        "process_terminated": True,
        "process_crash": True,
        "crash_source": f"controlled-causal-{name.lower().replace(' ', '-')}",
        "test_id": str(uuid.uuid4())[:8],

        "processes": [
            {
                "pid": pid,
                "name": "controlled-test-process.exe",
                "cpu_percent": float(process_cpu),
                "memory_percent": float(memory / 4.0),
                "status": "terminated-after-crash",
                "node": "local",
                "cpu": float(process_cpu),
                "memory": float(memory / 4.0),
            }
        ],

        "global_top_process": {
            "pid": pid,
            "name": "controlled-test-process.exe",
            "cpu_percent": float(process_cpu),
            "memory_percent": float(memory / 4.0),
            "status": "terminated-after-crash",
        },

        "application_attribution": [
            {
                "pid": pid,
                "name": "controlled-test-process.exe",
                "role": "controlled-crash-process",
            }
        ],
    }

    result = run_intelligence_pipeline(
        allow_execution=False,
        live_metrics=live_metrics,
    )

    observed = extract(result)

    print()
    print("CLASSIFICATION:")
    print(json.dumps(observed, indent=2, default=str))

    print()
    print("EXECUTION SAFETY:")
    print(f"auto_execute          = {observed['auto_execute']}")
    print(f"requires_confirmation = {observed['requires_confirmation']}")

    assert observed["auto_execute"] is False, (
        f"{name}: auto_execute unexpectedly became True"
    )

    assert observed["requires_confirmation"] is True, (
        f"{name}: requires_confirmation unexpectedly became False"
    )

    print()
    print("EXPECTED ROOT-CAUSE TYPES:")
    print(expected_root_types)

    print("OBSERVED ROOT-CAUSE TYPE:")
    print(observed["root_cause_type"])

    assert observed["root_cause_type"] in expected_root_types, (
        f"{name}: unexpected root cause. "
        f"Observed={observed['root_cause_type']!r}, "
        f"Expected={expected_root_types}"
    )

    print(f"PASS: {name}")


def main():
    print()
    print("=== CONTROLLED CAUSAL DISCRIMINATION TEST ===")
    print()
    print("Three isolated causal scenarios:")
    print("  A. CPU pressure")
    print("  B. Memory pressure")
    print("  C. Normal resources + application crash")
    print()
    print("Execution is explicitly disabled.")

    # ---------------------------------------------------------------
    # CASE A
    # ---------------------------------------------------------------
    run_case(
        name="CPU PRESSURE",
        cpu=99.0,
        memory=40.0,
        process_cpu=100.0,
        expected_root_types={
            "cpu_overload",
        },
    )

    # ---------------------------------------------------------------
    # CASE B
    # ---------------------------------------------------------------
    run_case(
        name="MEMORY PRESSURE",
        cpu=20.0,
        memory=95.0,
        process_cpu=5.0,
        expected_root_types={
            "memory_pressure",
        },
    )

    # ---------------------------------------------------------------
    # CASE C
    # ---------------------------------------------------------------
    run_case(
        name="NORMAL RESOURCE APPLICATION CRASH",
        cpu=25.0,
        memory=40.0,
        process_cpu=20.0,
        expected_root_types={
            "application_failure",
            "process_failure",
            "application_crash",
            "process_crash",
            "software_failure",
            "unknown",
        },
    )

    print()
    print("=" * 80)
    print("ALL THREE CAUSAL DISCRIMINATION CASES PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()
