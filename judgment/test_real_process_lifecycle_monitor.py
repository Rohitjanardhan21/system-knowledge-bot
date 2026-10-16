import multiprocessing as mp
import time

import psutil

from backend.core.process_lifecycle import ProcessLifecycleMonitor


def real_child():
    time.sleep(30)


def main():
    print("=== REAL PROCESS LIFECYCLE DETECTION REGRESSION ===")
    print("REAL PROCESS.")
    print("REAL PSUTIL OBSERVATION.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO FAILUREDNA.")
    print("NO DATABASE CHANGES.")

    monitor = ProcessLifecycleMonitor()

    child = mp.Process(target=real_child)
    child.start()

    proc = psutil.Process(child.pid)

    try:
        create_time = proc.create_time()
        name = proc.name()
        exe = proc.exe()
        ppid = proc.ppid()

        print("\n1. REAL CHILD")
        print("   PID:", child.pid)
        print("   create_time:", create_time)
        print("   name:", name)
        print("   exe:", exe)
        print("   ppid:", ppid)

        assert proc.is_running()

        print("\n2. INITIAL OBSERVATION")

        events = monitor.observe_and_detect()

        assert events == []

        matching = [
            identity
            for identity in monitor.tracked_identities()
            if identity.pid == child.pid
            and identity.create_time == create_time
        ]

        assert len(matching) == 1

        print("PASS: Real process tracked by exact identity.")

        print("\n3. REAL ABNORMAL TERMINATION")

        child.terminate()

        exit_code = proc.wait(timeout=5)

        print("   psutil exit_code:", exit_code)
        print("   multiprocessing exitcode:", child.exitcode)

        assert exit_code is not None
        assert exit_code != 0

        print("PASS: Real abnormal termination confirmed.")

        print("\n4. POST-TERMINATION OBSERVATION")

        time.sleep(0.5)

        events = monitor.observe_and_detect()

        print("   detected events:", len(events))

        for event in events:
            print("   event:", event)

        matching_events = [
            event
            for event in events
            if event["pid"] == child.pid
            and event["create_time"] == create_time
        ]

        assert len(matching_events) == 1

        event = matching_events[0]

        assert event["event_type"] == "PROCESS_CRASH"
        assert event["pid"] == child.pid
        assert event["create_time"] == create_time
        assert event["name"] == name
        assert event["exe"] == exe
        assert event["ppid"] == ppid
        assert event["exit_code"] == exit_code
        assert event["expected"] is False

        print("PASS: Real child classified as PROCESS_CRASH.")

        print("\n5. FALSE-POSITIVE GUARD")

        unrelated = [
            event
            for event in events
            if event["pid"] != child.pid
        ]

        print("   unrelated crash events:", len(unrelated))

        assert unrelated == []

        print("PASS: No unrelated process was classified as a crash.")

        print("\n6. EXACTLY-ONCE")

        second_events = monitor.observe_and_detect()

        print("   second observation events:", len(second_events))

        assert second_events == []

        print("PASS: No duplicate event.")

        print("\n7. FINAL RESULT")
        print("REAL PROCESS TERMINATION DETECTED.")
        print("REAL EXIT CODE CAPTURED.")
        print("PID + CREATE_TIME IDENTITY PRESERVED.")
        print("NO DISAPPEARANCE-ONLY CRASH.")
        print("NO UNRELATED CRASH.")
        print("EXACTLY-ONCE DETECTION.")
        print("RESULT: PASS")

    finally:
        if child.is_alive():
            child.terminate()

        child.join(timeout=5)


if __name__ == "__main__":
    mp.freeze_support()
    main()
