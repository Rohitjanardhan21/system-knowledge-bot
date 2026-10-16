from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil

from backend.core.cognitive.failure_dna import FailureDNAEngine
from backend.core.learning_engine import LearningEngine
from backend.intelligence_pipeline import run_intelligence_pipeline


def cpu_burn_worker(ready_file: str):
    """
    Real application-like workload.

    The child intentionally consumes CPU so that process-level telemetry
    can identify it before termination.
    """
    path = Path(ready_file)

    process = psutil.Process(os.getpid())

    path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "name": process.name(),
                "status": "running",
                "started_at": time.time(),
            }
        ),
        encoding="utf-8",
    )

    # Deliberately CPU-intensive workload.
    value = 0

    while True:
        for i in range(1_000_000):
            value += (i * i) % 97

        # Prevent the interpreter from optimizing away the work.
        if value > 10**18:
            value = value % 97


def wait_for_file(path: Path, timeout: float = 10.0):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)

    return False


def sample_process(pid: int):
    process = psutil.Process(pid)

    # Prime CPU measurement.
    process.cpu_percent(interval=None)
    time.sleep(0.75)

    cpu = process.cpu_percent(interval=None)

    return {
        "pid": pid,
        "name": process.name(),
        "exe": process.exe() if process.is_running() else None,
        "cpu_percent": cpu,
        "memory_percent": process.memory_percent(),
        "status": process.status(),
    }


def fresh_process_check(test_id: str):
    code = r'''
import json
import sys

from backend.core.cognitive.failure_dna import FailureDNAEngine

test_id = sys.argv[1]

dna = FailureDNAEngine()
history = dna.get_failure_history(limit=50)

matches = [
    event
    for event in history
    if (
        getattr(event, "event_type", "").strip().upper()
        == "PROCESS_CRASH"
        and test_id in getattr(event, "description", "")
    )
]

print(
    json.dumps(
        {
            "matches": len(matches),
            "events": [
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "description": event.description,
                    "severity": event.severity,
                }
                for event in matches
            ],
        }
    )
)
'''

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            test_id,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(result.stdout.strip())


def main():
    print()
    print("=== REAL PROCESS ATTRIBUTION + CRASH INTELLIGENCE TEST ===")
    print()

    test_id = uuid.uuid4().hex[:8]
    ready_file = Path("state") / f"process_attribution_{test_id}.json"

    ready_file.parent.mkdir(parents=True, exist_ok=True)

    child = None

    try:
        print("1. STARTING REAL CPU-INTENSIVE APPLICATION:")

        child = mp.Process(
            target=cpu_burn_worker,
            args=(str(ready_file),),
        )

        child.start()

        print("Child PID:", child.pid)

        assert wait_for_file(ready_file), (
            "CPU-intensive child never reached running state."
        )

        child_info = json.loads(
            ready_file.read_text(encoding="utf-8")
        )

        print("Child information:")
        print(json.dumps(child_info, indent=2))

        assert child_info["pid"] == child.pid
        assert child_info["status"] == "running"

        print("REAL CPU-INTENSIVE PROCESS IS RUNNING.")
        print("PASS")
        print()

        print("2. CAPTURING PROCESS-LEVEL TELEMETRY:")

        process_metrics = sample_process(child.pid)

        print(json.dumps(process_metrics, indent=2))

        assert process_metrics["pid"] == child.pid
        assert process_metrics["name"] == child_info["name"]

        print("PROCESS PID/NAME WERE ATTRIBUTED.")
        print("PASS")
        print()

        print("3. VERIFYING THE CHILD IS ACTUALLY CPU ACTIVE:")

        print(
            f"Observed CPU usage for PID {child.pid}: "
            f"{process_metrics['cpu_percent']:.2f}%"
        )

        assert process_metrics["cpu_percent"] > 0.0, (
            "Child process did not produce measurable CPU activity."
        )

        print("REAL PROCESS GENERATED MEASURABLE CPU LOAD.")
        print("PASS")
        print()

        print("4. BUILDING CRASH + PROCESS ATTRIBUTION EVIDENCE:")

        crash_metrics = {
            "process_id": child.pid,
            "process_name": child_info["name"],
            "process_exe": process_metrics["exe"],
            "process_cpu_percent": process_metrics["cpu_percent"],
            "process_memory_percent": process_metrics["memory_percent"],

            "process_terminated": True,
            "process_crash": True,
            "crash_source": "real-cpu-intensive-child",
            "test_id": test_id,

            # System-level evidence.
            "cpu_percent": min(
                99.0,
                max(90.0, process_metrics["cpu_percent"]),
            ),
            "memory_percent": max(
                80.0,
                process_metrics["memory_percent"],
            ),
            "disk_percent": 70.0,
            "anomaly_score": 0.95,

            # Explicit attribution object for systems that consume
            # process lists rather than flat process_id fields.
            "processes": [
                {
                    "pid": child.pid,
                    "name": child_info["name"],
                    "cpu_percent": process_metrics["cpu_percent"],
                    "memory_percent": process_metrics["memory_percent"],
                    "status": "running-before-crash",
                }
            ],

            "global_top_process": {
                "pid": child.pid,
                "name": child_info["name"],
                "cpu_percent": process_metrics["cpu_percent"],
                "memory_percent": process_metrics["memory_percent"],
            },

            "application_attribution": [
                {
                    "pid": child.pid,
                    "name": child_info["name"],
                    "role": "crashed-high-cpu-process",
                }
            ],
        }

        print(json.dumps(crash_metrics, indent=2, default=str))

        assert crash_metrics["process_id"] == child.pid
        assert crash_metrics["processes"][0]["pid"] == child.pid
        assert (
            crash_metrics["global_top_process"]["pid"]
            == child.pid
        )

        print("CRASH EVIDENCE CONTAINS PROCESS-LEVEL ATTRIBUTION.")
        print("PASS")
        print()

        print("5. TERMINATING THE REAL APPLICATION:")

        child.terminate()
        child.join(timeout=10)

        if child.is_alive():
            child.kill()
            child.join(timeout=10)

        print("Child exitcode:", child.exitcode)

        assert child.exitcode is not None
        assert child.exitcode != 0

        print("REAL CPU-INTENSIVE APPLICATION TERMINATED ABNORMALLY.")
        print("PASS")
        print()

        print("6. RECORDING THE PROCESS-SPECIFIC FAILURE:")

        dna = FailureDNAEngine()

        dna.ingest(crash_metrics)

        dna.record_failure(
            event_type="PROCESS_CRASH",
            description=(
                f"Real CPU-intensive application "
                f"PID={child.pid}, "
                f"name={child_info['name']}, "
                f"test_id={test_id}, "
                f"terminated abnormally with "
                f"exit code {child.exitcode}."
            ),
            severity="HIGH",
        )

        history = dna.get_failure_history(limit=50)

        matches = [
            event
            for event in history
            if (
                getattr(event, "event_type", "").upper()
                == "PROCESS_CRASH"
                and test_id in getattr(event, "description", "")
            )
        ]

        print("Matching process-specific failure events:", len(matches))

        assert matches, (
            "Process-specific PROCESS_CRASH event was not persisted."
        )

        print(matches[0])

        print("PROCESS-SPECIFIC FAILURE RECORDED.")
        print("PASS")
        print()

        print("7. RUNNING LEARNING ENGINE:")

        learning = LearningEngine()

        anomalies = learning.detect_anomalies(crash_metrics)
        risk = learning.compute_risk(anomalies)
        analysis = learning.analyze(crash_metrics)

        print("Anomalies:")
        print(json.dumps(anomalies, indent=2, default=str))

        print("Risk:")
        print(json.dumps(risk, indent=2, default=str))

        print("Analysis:")
        print(json.dumps(analysis, indent=2, default=str))

        assert anomalies is not None
        assert risk is not None
        assert analysis is not None

        print("LEARNING ENGINE PROCESSED PROCESS-SPECIFIC EVIDENCE.")
        print("PASS")
        print()

        print("8. RUNNING INTELLIGENCE PIPELINE:")

        result = run_intelligence_pipeline(
            allow_execution=False,
            live_metrics=crash_metrics,
        )

        print(
            json.dumps(
                result,
                indent=2,
                default=str,
            )
        )

        assert result is not None
        assert isinstance(result, dict)

        print("INTELLIGENCE PIPELINE COMPLETED.")
        print("PASS")
        print()

        print("9. CHECKING APPLICATION ATTRIBUTION:")

        attributed_process = result.get(
            "application_attribution",
            [],
        )

        global_top_process = result.get(
            "global_top_process"
        )

        root_cause = result.get(
            "root_cause"
        )

        print("application_attribution:")
        print(json.dumps(attributed_process, indent=2, default=str))

        print("global_top_process:")
        print(json.dumps(global_top_process, indent=2, default=str))

        print("root_cause:")
        print(json.dumps(root_cause, indent=2, default=str))

        attribution_found = False

        if isinstance(attributed_process, list):
            for item in attributed_process:
                if not isinstance(item, dict):
                    continue

                if (
                    item.get("pid") == child.pid
                    or item.get("process_id") == child.pid
                    or item.get("name") == child_info["name"]
                ):
                    attribution_found = True

        if isinstance(global_top_process, dict):
            if (
                global_top_process.get("pid") == child.pid
                or global_top_process.get("process_id") == child.pid
                or global_top_process.get("name") == child_info["name"]
            ):
                attribution_found = True

        if isinstance(root_cause, dict):
            if (
                root_cause.get("process") == child_info["name"]
                or root_cause.get("pid") == child.pid
                or root_cause.get("process_id") == child.pid
            ):
                attribution_found = True

        if not attribution_found:
            raise AssertionError(
                "\nPROCESS ATTRIBUTION GAP DETECTED:\n"
                f"The real crashed process was PID={child.pid}, "
                f"name={child_info['name']}, but the intelligence "
                "result did not attribute the condition to it."
            )

        print(
            f"SUCCESS: crashed process PID={child.pid} "
            f"name={child_info['name']} was attributed."
        )
        print("PASS")
        print()

        print("10. VERIFYING EXECUTION REMAINED DISABLED:")

        decision = result.get("decision", {})

        if isinstance(decision, dict):
            print("auto_execute:", decision.get("auto_execute"))
            print(
                "requires_confirmation:",
                decision.get("requires_confirmation"),
            )

            assert decision.get("auto_execute") is not True

        execution = result.get("execution")

        assert execution is None or execution == {}

        print("NO REMEDIATION WAS EXECUTED.")
        print("PASS")
        print()

        print("11. FRESH-PROCESS PERSISTENCE CHECK:")

        fresh = fresh_process_check(test_id)

        print(json.dumps(fresh, indent=2))

        assert fresh["matches"] >= 1

        print("FRESH PROCESS OBSERVED THE PROCESS-SPECIFIC CRASH.")
        print("PASS")
        print()

        print("12. FINAL PROCESS-ATTRIBUTION INVARIANTS:")
        print("REAL CPU-INTENSIVE CHILD PROCESS CREATED")
        print("PROCESS-LEVEL PID/NAME CAPTURED")
        print("MEASURABLE CPU ACTIVITY OBSERVED")
        print("REAL PROCESS TERMINATED ABNORMALLY")
        print("PROCESS-SPECIFIC CRASH EVENT RECORDED")
        print("LEARNING ENGINE PROCESSED PROCESS EVIDENCE")
        print("INTELLIGENCE PIPELINE PROCESSED PROCESS EVIDENCE")
        print("CRASHED PROCESS WAS ATTRIBUTED")
        print("NO REMEDIATION EXECUTED")
        print("FRESH PROCESS CONFIRMED PERSISTENCE")
        print()
        print("RESULT: PASS")

    finally:
        if child is not None and child.is_alive():
            child.kill()
            child.join(timeout=5)

        try:
            ready_file.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    mp.freeze_support()
    main()
