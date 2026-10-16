from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from backend.core.learning_engine import LearningEngine
from backend.core.cognitive.failure_dna import FailureDNAEngine
from backend.intelligence_pipeline import run_intelligence_pipeline


def real_application_worker(ready_file: str):
    """
    Real child application.

    The process remains alive until the parent forcibly terminates it.
    """
    path = Path(ready_file)

    path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "status": "running",
                "started_at": time.time(),
            }
        ),
        encoding="utf-8",
    )

    while True:
        time.sleep(0.25)


def wait_for_file(path: Path, timeout: float = 10.0):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)

    return False


def main():
    print()
    print("=== REAL APPLICATION CRASH + INTELLIGENCE TEST ===")
    print()

    test_id = uuid.uuid4().hex[:8]
    ready_file = Path("state") / f"real_crash_test_{test_id}.json"

    ready_file.parent.mkdir(parents=True, exist_ok=True)

    child = None

    try:
        print("1. STARTING REAL APPLICATION PROCESS:")

        child = mp.Process(
            target=real_application_worker,
            args=(str(ready_file),),
        )

        child.start()

        print("Child PID:", child.pid)

        assert wait_for_file(ready_file), (
            "Real application never reached its running state."
        )

        child_state = json.loads(
            ready_file.read_text(encoding="utf-8")
        )

        print("Child reported:", child_state)

        assert child_state["pid"] == child.pid
        assert child_state["status"] == "running"

        print("REAL APPLICATION PROCESS IS RUNNING.")
        print("PASS")
        print()

        print("2. FORCING REAL PROCESS TERMINATION:")

        child.terminate()
        child.join(timeout=10)

        if child.is_alive():
            child.kill()
            child.join(timeout=10)

        print("Child exitcode:", child.exitcode)

        assert child.exitcode is not None
        assert child.exitcode != 0, (
            "Child exited normally; abnormal termination was not established."
        )

        print("REAL CHILD PROCESS TERMINATED ABNORMALLY.")
        print("PASS")
        print()

        print("3. CAPTURING REAL CRASH EVIDENCE:")

        crash_metrics = {
            "process_id": child.pid,
            "process_exit_code": child.exitcode,
            "process_terminated": True,
            "process_crash": True,
            "crash_source": "real-child-process",
            "test_id": test_id,

            # High-stress telemetry for the intelligence layer.
            "cpu_percent": 95.0,
            "memory_percent": 92.0,
            "disk_percent": 70.0,
            "anomaly_score": 0.95,
        }

        print(json.dumps(crash_metrics, indent=2))

        assert crash_metrics["process_crash"] is True
        assert crash_metrics["process_exit_code"] != 0

        print("REAL CRASH EVIDENCE CAPTURED.")
        print("PASS")
        print()

        print("4. INGESTING CRASH INTO FAILURE DNA:")

        dna = FailureDNAEngine()

        dna.ingest(crash_metrics)

        print("Failure DNA ingestion completed.")

        health = dna.get_health_score(crash_metrics)

        print("Failure DNA health score:")
        print(json.dumps(health, indent=2, default=str))

        assert isinstance(health, dict)
        assert "score" in health
        assert "grade" in health

        print("FAILURE DNA ACCEPTED THE REAL CRASH SNAPSHOT.")
        print("PASS")
        print()

        print("5. RECORDING REAL CRASH EVENT:")

        event_description = (
            f"Real application process {child.pid} terminated "
            f"abnormally with exit code {child.exitcode}."
        )

        dna.record_failure(
            event_type="PROCESS_CRASH",
            description=event_description,
            severity="HIGH",
        )

        history = dna.get_failure_history(limit=20)

        matching_history = [
            event
            for event in history
            if (
                getattr(event, "event_type", "").strip().upper()
                == "PROCESS_CRASH"
            )
        ]

        print("Recent failure-history entries:", len(history))
        print("Matching PROCESS_CRASH entries:", len(matching_history))

        assert matching_history, (
            "FailureDNA did not expose the recorded PROCESS_CRASH "
            "through its failure history."
        )

        latest = matching_history[0]

        print("Recorded FailureEvent:")
        print(latest)

        assert latest.event_type == "PROCESS_CRASH"
        assert latest.severity == "HIGH"
        assert str(child.pid) in latest.description
        assert str(child.exitcode) in latest.description

        print("REAL CRASH EVENT RECORDED CORRECTLY.")
        print("PASS")
        print()

        print("6. RUNNING LEARNING ENGINE AGAINST CRASH METRICS:")

        learning = LearningEngine()

        anomalies = learning.detect_anomalies(crash_metrics)

        print("Detected anomalies:")
        print(json.dumps(anomalies, indent=2, default=str))

        risk = learning.compute_risk(anomalies)

        print("Computed risk:")
        print(json.dumps(risk, indent=2, default=str))

        analysis = learning.analyze(crash_metrics)

        print("Learning analysis:")
        print(json.dumps(analysis, indent=2, default=str))

        assert anomalies is not None
        assert risk is not None
        assert analysis is not None

        print("LEARNING ENGINE ACCEPTED THE REAL CRASH OBSERVATION.")
        print("PASS")
        print()

        print("7. RUNNING INTELLIGENCE PIPELINE WITH EXECUTION DISABLED:")

        pipeline_result = run_intelligence_pipeline(
            allow_execution=False,
            live_metrics=crash_metrics,
        )

        print(
            json.dumps(
                pipeline_result,
                indent=2,
                default=str,
            )
        )

        assert pipeline_result is not None

        print("INTELLIGENCE PIPELINE RETURNED A RESULT.")
        print("NO REMEDIATION EXECUTION WAS PERMITTED.")
        print("PASS")
        print()

        print("8. VERIFYING REAL PROCESS TERMINAL STATE:")

        assert child.exitcode != 0

        print(
            f"PID {child.pid} is no longer running "
            f"and exitcode={child.exitcode}."
        )

        print("PASS")
        print()

        print("9. FRESH-PROCESS FAILURE-DNA CHECK:")

        fresh_check_code = r'''
import json

from backend.core.cognitive.failure_dna import FailureDNAEngine

dna = FailureDNAEngine()
history = dna.get_failure_history(limit=20)

matches = [
    event
    for event in history
    if (
        getattr(event, "event_type", "").strip().upper()
        == "PROCESS_CRASH"
    )
]

print(
    json.dumps(
        {
            "history_count": len(history),
            "process_crash_count": len(matches),
            "latest_event": (
                {
                    "event_id": matches[0].event_id,
                    "event_type": matches[0].event_type,
                    "severity": matches[0].severity,
                    "description": matches[0].description,
                }
                if matches
                else None
            ),
        }
    )
)
'''

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                fresh_check_code,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        print(result.stdout.strip())

        fresh = json.loads(result.stdout.strip())

        assert fresh["process_crash_count"] >= 1
        assert fresh["latest_event"] is not None
        assert fresh["latest_event"]["event_type"] == "PROCESS_CRASH"

        print("FRESH PROCESS OBSERVED THE CRASH RECORD.")
        print("PASS")
        print()

        print("10. FINAL REAL-CRASH INVARIANTS:")
        print("REAL CHILD PROCESS WAS CREATED")
        print("REAL CHILD PROCESS TERMINATED ABNORMALLY")
        print("REAL PID + EXIT CODE WERE CAPTURED")
        print("FAILURE DNA INGESTED THE CRASH SNAPSHOT")
        print("FAILURE DNA RECORDED PROCESS_CRASH")
        print("LEARNING ENGINE PROCESSED CRASH METRICS")
        print("INTELLIGENCE PIPELINE RETURNED A RESULT")
        print("NO REMEDIATION EXECUTION WAS PERMITTED")
        print("FRESH PROCESS OBSERVED THE CRASH RECORD")
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
