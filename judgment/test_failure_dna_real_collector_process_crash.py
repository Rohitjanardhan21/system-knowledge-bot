import asyncio
import multiprocessing as mp
import os
import time

from backend.main import app
from backend.core.cognitive.failure_dna import get_dna_engine


def real_cpu_process():
    print(f"REAL CHILD STARTED: PID={os.getpid()}", flush=True)

    value = 0
    while True:
        value = (value + 1) % 1000000007


def process_crash_events(engine):
    return [
        event
        for event in engine.get_failure_history(limit=200)
        if getattr(event, "event_type", None) == "PROCESS_CRASH"
    ]


async def run():
    print("=== REAL PRODUCTION COLLECTOR PROCESS-CRASH DETECTION TEST ===")
    print()
    print("REAL PROCESS.")
    print("REAL PRODUCTION COLLECTOR.")
    print("REAL FAILUREDNA HISTORY.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO MANUAL record_failure().")
    print("NO PREDICTION INJECTION.")
    print("NO REMEDIATION.")
    print()

    dna = get_dna_engine()

    before_events = process_crash_events(dna)

    print("1. INITIAL FAILUREDNA STATE")
    print("   PROCESS_CRASH events:", len(before_events))

    ctx = mp.get_context("spawn")
    child = ctx.Process(target=real_cpu_process)

    child.start()
    pid = child.pid

    assert pid is not None

    print()
    print("2. REAL CHILD STARTED")
    print("   PID:", pid)

    try:
        # Give the production lifespan/collector enough time to run
        # several normal collection cycles while the real process exists.
        print()
        print("3. ALLOWING PRODUCTION COLLECTOR TO OBSERVE LIVE PROCESS")

        for i in range(4):
            await asyncio.sleep(2.0)

            alive = child.is_alive()

            print(
                f"   observation window {i + 1}: "
                f"child_alive={alive}"
            )

            assert alive, (
                "Real child terminated before the intentional termination point."
            )

        # ---------------------------------------------------------
        # Capture FailureDNA state immediately before termination.
        # ---------------------------------------------------------
        before_termination_events = process_crash_events(dna)

        print()
        print("4. FAILUREDNA BEFORE CHILD TERMINATION")
        print(
            "   PROCESS_CRASH events:",
            len(before_termination_events),
        )

        # ---------------------------------------------------------
        # Intentionally terminate the real process.
        # ---------------------------------------------------------
        print()
        print("5. TERMINATING REAL CHILD")

        child.terminate()
        child.join(timeout=5)

        print("   exitcode:", child.exitcode)

        assert child.exitcode is not None
        assert child.exitcode != 0, (
            "Expected abnormal termination, but child exitcode was 0."
        )

        print("PASS: Real child terminated abnormally.")

        # ---------------------------------------------------------
        # Keep the production collector alive after termination.
        # ---------------------------------------------------------
        print()
        print("6. ALLOWING PRODUCTION COLLECTOR TO OBSERVE POST-TERMINATION STATE")

        for i in range(5):
            await asyncio.sleep(2.0)

            events = process_crash_events(dna)

            print(
                f"   post-termination window {i + 1}: "
                f"PROCESS_CRASH events={len(events)}"
            )

        # ---------------------------------------------------------
        # Final FailureDNA inspection.
        # ---------------------------------------------------------
        after_events = process_crash_events(dna)

        new_events = [
            event
            for event in after_events
            if event not in before_events
        ]

        matching_pid_events = [
            event
            for event in new_events
            if str(pid) in str(getattr(event, "description", ""))
        ]

        print()
        print("7. FINAL FAILUREDNA RESULT")
        print("   PROCESS_CRASH before test:", len(before_events))
        print("   PROCESS_CRASH after test:", len(after_events))
        print("   new PROCESS_CRASH events:", len(new_events))
        print("   new events mentioning PID:", len(matching_pid_events))

        if matching_pid_events:
            print()
            print("   MATCHING AUTOMATIC CRASH EVENTS:")
            for event in matching_pid_events:
                print("   ", event)

        # ---------------------------------------------------------
        # This is the actual architectural assertion.
        # ---------------------------------------------------------
        print()
        print("8. ARCHITECTURAL ASSERTION")

        if matching_pid_events:
            print(
                "PASS: Production collector automatically generated "
                "PROCESS_CRASH for the real terminated process."
            )
        else:
            print(
                "CONFIRMED GAP: Production collector did not generate "
                "PROCESS_CRASH for the real terminated process."
            )
            print(
                "The collector observes telemetry and invokes "
                "FailureDNA ingestion/prediction, but no automatic "
                "process-disappearance -> PROCESS_CRASH path was observed."
            )

            raise AssertionError(
                "Production collector did not automatically generate "
                "PROCESS_CRASH for a real terminated process."
            )

    finally:
        if child.is_alive():
            child.terminate()

        child.join(timeout=5)

        if child.is_alive():
            child.kill()
            child.join(timeout=5)

        print()
        print("9. REAL CHILD CLEANUP")
        print("   exitcode:", child.exitcode)


if __name__ == "__main__":
    mp.freeze_support()
    asyncio.run(run())
