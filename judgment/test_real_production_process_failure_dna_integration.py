import multiprocessing as mp
import os
import time
from pathlib import Path

import psutil

from backend.main import lifespan, app, COGNITIVE_OK, PROCESS_LIFECYCLE_OK
from backend.core.cognitive.failure_dna import get_dna_engine


def real_crashing_child():
    time.sleep(30)


def main():
    print("=== REAL PRODUCTION PROCESS -> FAILUREDNA INTEGRATION TEST ===")
    print("REAL PROCESS.")
    print("REAL PRODUCTION COLLECTOR.")
    print("REAL PSUTIL IDENTITY.")
    print("REAL FAILUREDNA.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO MANUAL record_failure().")
    print("NO PREDICTION INJECTION.")
    print("NO REMEDIATION.")

    assert COGNITIVE_OK, "Cognitive layer unavailable"
    assert PROCESS_LIFECYCLE_OK, "Process lifecycle monitor unavailable"

    dna = get_dna_engine()

    before = dna.get_failure_history(limit=1000)
    before_ids = {
        e.event_id
        for e in before
        if getattr(e, "event_type", None) == "PROCESS_CRASH"
    }

    print("\n1. INITIAL FAILUREDNA STATE")
    print("   PROCESS_CRASH events:", len(before_ids))

    child = mp.Process(target=real_crashing_child)
    child.start()

    target = psutil.Process(child.pid)

    try:
        identity = {
            "pid": target.pid,
            "create_time": target.create_time(),
            "name": target.name(),
            "exe": target.exe(),
            "ppid": target.ppid(),
        }

        print("\n2. REAL CHILD STARTED")
        for key, value in identity.items():
            print(f"   {key}: {value}")

        # Give the actual production collector time to observe the child.
        tracked = False

        print("\n3. WAITING FOR PRODUCTION COLLECTOR TO TRACK CHILD")
        for attempt in range(15):
            try:
                tracked_process = psutil.Process(child.pid)
                tracked_identity = (
                    tracked_process.pid,
                    tracked_process.create_time(),
                )
            except psutil.NoSuchProcess:
                tracked_identity = None

            monitor = __import__(
                "backend.core.process_lifecycle",
                fromlist=["get_process_lifecycle_monitor"],
            ).get_process_lifecycle_monitor()

            tracked_keys = {
                (x.pid, x.create_time)
                for x in monitor.tracked_identities()
            }

            if tracked_identity in tracked_keys:
                tracked = True
                print(
                    f"PASS: Collector lifecycle monitor tracked "
                    f"PID {child.pid} with exact PID + create_time."
                )
                break

            print(
                f"   collector observation {attempt + 1}: "
                f"target_tracked={tracked_identity in tracked_keys}"
            )
            time.sleep(1)

        assert tracked, (
            "Production collector did not track the real child "
            "with PID + create_time before termination."
        )

        before_termination = dna.get_failure_history(limit=1000)
        before_termination_ids = {
            e.event_id
            for e in before_termination
            if getattr(e, "event_type", None) == "PROCESS_CRASH"
        }

        print("\n4. FAILUREDNA BEFORE TERMINATION")
        print(
            "   PROCESS_CRASH events:",
            len(before_termination_ids),
        )

        print("\n5. REAL ABNORMAL TERMINATION")
        target.terminate()
        child.join(timeout=10)

        print("   multiprocessing exitcode:", child.exitcode)

        assert child.exitcode is not None
        assert child.exitcode != 0
        print("PASS: Real child terminated abnormally.")

        # The production collector must discover the termination itself.
        print("\n6. WAITING FOR PRODUCTION COLLECTOR TO DETECT CRASH")

        detected_event = None

        for attempt in range(15):
            history = dna.get_failure_history(limit=1000)

            candidates = [
                e for e in history
                if getattr(e, "event_type", None) == "PROCESS_CRASH"
                and getattr(e, "event_id", None) not in before_termination_ids
                and str(child.pid) in getattr(e, "description", "")
            ]

            if candidates:
                detected_event = candidates[0]
                print(
                    f"PASS: Production collector generated "
                    f"PROCESS_CRASH on observation {attempt + 1}."
                )
                break

            print(
                f"   collector observation {attempt + 1}: "
                f"target PROCESS_CRASH not yet persisted"
            )
            time.sleep(1)

        assert detected_event is not None, (
            "Production collector failed to generate and persist "
            "PROCESS_CRASH for the real terminated process."
        )

        print("\n7. REAL FAILUREDNA EVENT")
        print("   event_id:", detected_event.event_id)
        print("   event_type:", detected_event.event_type)
        print("   severity:", detected_event.severity)
        print("   description:", detected_event.description)

        assert detected_event.event_type == "PROCESS_CRASH"
        assert str(child.pid) in detected_event.description
        assert "create_time" in detected_event.description
        assert "exit code" in detected_event.description

        # Exactly-once check.
        time.sleep(2)

        history_after = dna.get_failure_history(limit=1000)
        matching = [
            e for e in history_after
            if getattr(e, "event_type", None) == "PROCESS_CRASH"
            and str(child.pid) in getattr(e, "description", "")
        ]

        print("\n8. EXACTLY-ONCE CHECK")
        print("   matching PROCESS_CRASH events:", len(matching))

        assert len(matching) == 1, (
            f"Expected exactly one PROCESS_CRASH for PID {child.pid}, "
            f"found {len(matching)}"
        )

        # Fresh process verification:
        # load FailureDNA from its durable file in a new Python process.
        print("\n9. FRESH PROCESS PERSISTENCE CHECK")

        import subprocess
        import sys

        code = r'''
from backend.core.cognitive.failure_dna import get_dna_engine

dna = get_dna_engine()
events = [
    e for e in dna.get_failure_history(limit=1000)
    if getattr(e, "event_type", None) == "PROCESS_CRASH"
]

print("FRESH_PROCESS_PROCESS_CRASH_COUNT:", len(events))

for e in events:
    description = getattr(e, "description", "")
    if "TARGET_PID_MARKER" in description:
        print("TARGET_EVENT_FOUND:", e.event_id)
        print("TARGET_EVENT_TYPE:", e.event_type)
        print("TARGET_DESCRIPTION:", description)
        raise SystemExit(0)

raise SystemExit(2)
'''.replace("TARGET_PID_MARKER", str(child.pid))

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )

        print(result.stdout.strip())

        if result.stderr.strip():
            print("fresh-process stderr:")
            print(result.stderr.strip())

        assert result.returncode == 0, (
            "Fresh Python process could not observe the persisted "
            "PROCESS_CRASH event."
        )

        print("\n10. FINAL RESULT")
        print("REAL CHILD PROCESS: PASS")
        print("REAL PROCESS IDENTITY: PASS")
        print("REAL ABNORMAL TERMINATION: PASS")
        print("PRODUCTION COLLECTOR DETECTION: PASS")
        print("FAILUREDNA RECORDING: PASS")
        print("FAILUREDNA PERSISTENCE: PASS")
        print("EXACTLY-ONCE DETECTION: PASS")
        print("FRESH PROCESS VERIFICATION: PASS")
        print("RESULT: PASS")

    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)


if __name__ == "__main__":
    mp.freeze_support()

    async def run():
        async with lifespan(app):
            main()

    import asyncio
    asyncio.run(run())
