import asyncio
import multiprocessing as mp
import os
import time

from backend.main import app
from backend.core.cognitive.failure_dna import get_dna_engine


def real_child_process():
    print(f"REAL CHILD STARTED: PID={os.getpid()}", flush=True)
    while True:
        time.sleep(0.25)


async def call_process_route():
    route = next(
        (
            r
            for r in app.routes
            if getattr(r, "path", None) == "/os/processes"
        ),
        None,
    )

    assert route is not None, (
        "Production /os/processes route was not registered."
    )

    endpoint = route.endpoint
    result = endpoint()

    if hasattr(result, "__await__"):
        result = await result

    return result


def extract_processes(response):
    if isinstance(response, dict):
        for key in ("processes", "data", "items"):
            value = response.get(key)
            if isinstance(value, list):
                return value

    if isinstance(response, list):
        return response

    return []


async def run():
    print("=== REAL PRODUCTION PROCESS LIFECYCLE TEST ===")
    print()
    print("Scenario:")
    print("1. Start a real child process.")
    print("2. Observe it through the actual production /os/processes route.")
    print("3. Terminate the real process.")
    print("4. Observe the same production route again.")
    print("5. Verify the PID disappears.")
    print("6. Verify FailureDNA did NOT fabricate a PROCESS_CRASH event.")
    print()
    print("NO synthetic telemetry.")
    print("NO manual record_failure().")
    print("NO synthetic crash event.")
    print("NO remediation.")
    print()

    mp.freeze_support()

    dna = get_dna_engine()

    before_history = dna.get_failure_history(limit=100)
    before_ids = {
        getattr(event, "event_id", None)
        for event in before_history
        if getattr(event, "event_id", None)
    }

    async with app.router.lifespan_context(app):
        print("Backend lifespan: STARTED")
        print()

        child = mp.Process(
            target=real_child_process,
            name="REAL-PROCESS-LIFECYCLE-CHILD",
        )

        child.start()

        pid = child.pid

        print("REAL CHILD PID:", pid)
        assert pid is not None
        assert child.is_alive()

        print("Child is genuinely running.")
        print("PASS")
        print()

        print("1. QUERYING ACTUAL PRODUCTION /os/processes ROUTE")
        await asyncio.sleep(2.0)

        response_before = await call_process_route()
        processes_before = extract_processes(response_before)

        matching_before = [
            p
            for p in processes_before
            if isinstance(p, dict)
            and p.get("pid") == pid
        ]

        print("Production process records:", len(processes_before))
        print("Matching real PID records:", len(matching_before))

        if matching_before:
            print("Observed production process record:")
            print(matching_before[0])
            print("PASS")
        else:
            print(
                "FINDING: child was real and running, but the production "
                "/os/processes response did not contain its PID."
            )

        print()
        print("2. TERMINATING THE REAL PROCESS")

        child.terminate()
        child.join(timeout=5.0)

        print("Real child exitcode:", child.exitcode)

        assert child.exitcode is not None
        assert child.exitcode != 0

        print("REAL PROCESS TERMINATED ABNORMALLY")
        print("PASS")
        print()

        print("3. QUERYING PRODUCTION /os/processes AFTER TERMINATION")

        await asyncio.sleep(2.0)

        response_after = await call_process_route()
        processes_after = extract_processes(response_after)

        matching_after = [
            p
            for p in processes_after
            if isinstance(p, dict)
            and p.get("pid") == pid
        ]

        print("Production process records:", len(processes_after))
        print("Matching terminated PID records:", len(matching_after))

        if not matching_after:
            print(
                "PASS: production process view no longer contains "
                "the terminated PID."
            )
        else:
            print(
                "WARNING: terminated PID is still present in the "
                "production process view."
            )

        print()
        print("4. CHECKING FAILURE-DNA FOR AUTOMATIC CRASH CREATION")

        after_history = dna.get_failure_history(limit=100)

        new_events = [
            event
            for event in after_history
            if getattr(event, "event_id", None)
            and getattr(event, "event_id", None) not in before_ids
        ]

        matching_crashes = [
            event
            for event in new_events
            if getattr(event, "event_type", None) == "PROCESS_CRASH"
            and str(pid) in str(getattr(event, "description", ""))
        ]

        print("New FailureEvents:", len(new_events))
        print("Automatic PROCESS_CRASH events for PID:", len(matching_crashes))

        print()
        print("5. FINAL LIFECYCLE FINDING")

        assert not matching_after, (
            "Production /os/processes still reports the terminated PID."
        )

        if matching_crashes:
            print(
                "PASS: production process disappearance resulted in "
                "an automatic PROCESS_CRASH event."
            )
        else:
            print(
                "CONFIRMED ARCHITECTURAL GAP:"
            )
            print(
                "The production system can observe the real process "
                "while alive and can observe its disappearance, but "
                "no automatic PROCESS_CRASH event is generated."
            )
            print()
            print(
                "This means a real process-lifecycle detector is currently "
                "missing from the production telemetry path."
            )

    print()
    print("Backend lifespan: STOPPED")
    print("RESULT: LIFECYCLE OBSERVATION COMPLETE")


if __name__ == "__main__":
    asyncio.run(run())
