import asyncio
import multiprocessing as mp
import os
import time

from backend.main import app
from backend.core.cognitive.failure_dna import get_dna_engine


def real_child_process():
    print(f"REAL CHILD STARTED: PID={os.getpid()}", flush=True)

    # Keep the real process alive long enough for the production
    # collector to observe it.
    while True:
        time.sleep(0.25)


async def run():
    print("=== REAL PRODUCTION CRASH DETECTION TEST ===")
    print()
    print("REAL-LIFE SCENARIO:")
    print("The CVIS backend is running normally.")
    print("A real child application process starts.")
    print("The production collector gets time to observe the process.")
    print("The child then terminates abnormally.")
    print("We check whether the production system itself records PROCESS_CRASH.")
    print()
    print("IMPORTANT:")
    print("- No synthetic telemetry.")
    print("- No manual FailureDNA record_failure() call.")
    print("- No synthetic crash event.")
    print("- No remediation execution.")
    print()

    mp.freeze_support()

    dna = get_dna_engine()

    before = dna.get_failure_history(limit=100)

    before_ids = {
        getattr(event, "event_id", None)
        for event in before
        if getattr(event, "event_id", None)
    }

    print("Failure history before child launch:", len(before))
    print()

    child = mp.Process(
        target=real_child_process,
        name="REAL-CVIS-CRASH-DETECTION-CHILD",
    )

    async with app.router.lifespan_context(app):
        print("Backend lifespan: STARTED")
        print()

        child.start()

        print("Real child PID:", child.pid)

        assert child.is_alive(), (
            "Real child failed to start."
        )

        print("Real child state: RUNNING")
        print("PASS")
        print()

        # Give the real production collector time to observe the child.
        print("Allowing production collector to observe the real process...")
        await asyncio.sleep(3.0)

        print("Terminating the real child process...")
        child.terminate()
        child.join(timeout=5.0)

        print("Child exitcode:", child.exitcode)

        assert child.exitcode is not None
        assert child.exitcode != 0, (
            f"Child did not terminate abnormally: exitcode={child.exitcode}"
        )

        print("REAL CHILD TERMINATED ABNORMALLY")
        print("PASS")
        print()

        # Give the production collector time to process several
        # observations after the process disappeared.
        print("Waiting for production crash-detection processing...")
        await asyncio.sleep(4.0)

        after = dna.get_failure_history(limit=100)

        new_events = [
            event
            for event in after
            if getattr(event, "event_id", None)
            and getattr(event, "event_id", None) not in before_ids
        ]

        process_crashes = [
            event
            for event in new_events
            if getattr(event, "event_type", None) == "PROCESS_CRASH"
        ]

        print()
        print("=== PRODUCTION FAILURE HISTORY AFTER REAL CRASH ===")
        print("New FailureEvents:", len(new_events))
        print("New PROCESS_CRASH events:", len(process_crashes))

        for event in new_events:
            print(
                "EVENT:",
                getattr(event, "event_id", None),
                "| type=",
                getattr(event, "event_type", None),
                "| severity=",
                getattr(event, "severity", None),
                "| description=",
                getattr(event, "description", None),
            )

        print()
        print("=== RESULT ===")

        if process_crashes:
            print(
                "PASS: production FailureDNA recorded a PROCESS_CRASH "
                "without a manual record_failure() call."
            )
            print(
                "The system detected the real process failure through "
                "its production runtime path."
            )
        else:
            print(
                "FINDING: the real child process crashed, but the "
                "production pipeline did not create a PROCESS_CRASH event."
            )
            print(
                "This means the current production collector observes "
                "system telemetry but does not automatically attribute "
                "arbitrary process disappearance as a crash."
            )

    print()
    print("Backend lifespan: STOPPED")
    print("Real child cleanup complete.")


if __name__ == "__main__":
    asyncio.run(run())
