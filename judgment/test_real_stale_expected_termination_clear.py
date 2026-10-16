import multiprocessing as mp
import time
import psutil

from backend.core.process_lifecycle import get_process_lifecycle_monitor


def crash_process():
    # Real abnormal process termination.
    raise SystemExit(23)


def main():
    print("=== REAL STALE EXPECTED-AUTHORIZATION CLEARING TEST ===")
    print("REAL PROCESS.")
    print("REAL LIFECYCLE MONITOR.")
    print("REAL PROCESS IDENTITY.")
    print("NO SYNTHETIC PROCESS IDENTITIES.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO MANUAL FAILUREDNA EVENT INJECTION.")

    monitor = get_process_lifecycle_monitor()

    # ------------------------------------------------------------
    # 1. Start a real child process.
    # ------------------------------------------------------------
    child = mp.Process(target=crash_process)
    child.start()

    proc = psutil.Process(child.pid)

    identity = {
        "pid": proc.pid,
        "create_time": proc.create_time(),
        "name": proc.name(),
        "exe": proc.exe(),
    }

    print("\n1. REAL PROCESS IDENTITY:")
    print(identity)

    # ------------------------------------------------------------
    # 2. Make sure lifecycle monitor has actually observed it.
    # ------------------------------------------------------------
    tracked = False
    deadline = time.time() + 5

    while time.time() < deadline:
        monitor.observe_and_detect()

        for tracked_identity in monitor.tracked_identities():
            if (
                tracked_identity.pid == identity["pid"]
                and abs(
                    tracked_identity.create_time
                    - identity["create_time"]
                ) <= 0.01
            ):
                tracked = True
                break

        if tracked:
            break

        time.sleep(0.05)

    print("\n2. LIFECYCLE TRACKING:")
    print("tracked:", tracked)

    if not tracked:
        child.terminate()
        child.join(timeout=5)
        raise AssertionError("Real child was not tracked")

    # ------------------------------------------------------------
    # 3. Register expected termination.
    # ------------------------------------------------------------
    monitor.mark_expected_termination(
        identity["pid"],
        identity["create_time"],
    )

    expected_key = (
        identity["pid"],
        float(identity["create_time"]),
    )

    print("\n3. EXPECTED AUTHORIZATION:")
    print("authorized:", expected_key)

    if expected_key not in getattr(monitor, "_expected", set()):
        raise AssertionError(
            "Expected termination authorization was not registered"
        )

    # ------------------------------------------------------------
    # 4. Simulate termination-authority failure.
    #
    # We deliberately clear the authorization before the process
    # disappears. This models the production executor's failure
    # path after terminate() cannot be completed.
    # ------------------------------------------------------------
    print("\n4. TERMINATION FAILURE PATH:")
    print("simulating failed termination attempt")

    monitor.clear_expected_termination(
        identity["pid"],
        identity["create_time"],
    )

    if expected_key in getattr(monitor, "_expected", set()):
        raise AssertionError(
            "Expected authorization survived termination failure"
        )

    print("authorization cleared: PASS")

    # ------------------------------------------------------------
    # 5. Let the real process terminate abnormally.
    # ------------------------------------------------------------
    child.join(timeout=5)

    print("\n5. REAL PROCESS EXIT:")
    print("multiprocessing exitcode:", child.exitcode)

    if child.is_alive():
        child.terminate()
        child.join(timeout=5)
        raise AssertionError("Child did not exit")

    if child.exitcode == 0:
        raise AssertionError(
            "Child exited normally; abnormal termination was required"
        )

    # ------------------------------------------------------------
    # 6. Lifecycle monitor must now classify it as unexpected.
    # ------------------------------------------------------------
    events = monitor.observe_and_detect()

    print("\n6. LIFECYCLE RESULT:")
    print("events:", events)

    matching = [
        event
        for event in events
        if (
            event.get("pid") == identity["pid"]
            and abs(
                float(event.get("create_time", -1))
                - float(identity["create_time"])
            ) <= 0.01
        )
    ]

    if len(matching) != 1:
        raise AssertionError(
            f"Expected exactly one PROCESS_CRASH event, got {matching}"
        )

    event = matching[0]

    print("matching event:", event)

    if event.get("event_type") != "PROCESS_CRASH":
        raise AssertionError(
            f"Expected PROCESS_CRASH, got {event.get('event_type')}"
        )

    if event.get("expected") is not False:
        raise AssertionError(
            f"Expected expected=False, got {event.get('expected')}"
        )

    # ------------------------------------------------------------
    # 7. Exactly-once check.
    # ------------------------------------------------------------
    second_events = monitor.observe_and_detect()

    print("\n7. SECOND OBSERVATION:")
    print("events:", second_events)

    if second_events:
        raise AssertionError(
            "Same unexpected termination was reported more than once"
        )

    # ------------------------------------------------------------
    # Final invariants.
    # ------------------------------------------------------------
    print("\n8. FINAL AUTHORITY-BOUNDARY ASSERTIONS:")
    print("real process identity:", "PASS")
    print("real lifecycle tracking:", "PASS")
    print("expected authorization initially registered:", "PASS")
    print("failed termination clears authorization:", "PASS")
    print("real abnormal process exit:", "PASS")
    print("stale authorization did not suppress crash:", "PASS")
    print("PROCESS_CRASH generated exactly once:", "PASS")
    print("second observation produced no duplicate:", "PASS")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    mp.freeze_support()
    main()
