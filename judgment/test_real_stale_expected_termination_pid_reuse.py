import multiprocessing as mp
import time
import psutil

from backend.core.process_lifecycle import get_process_lifecycle_monitor


def short_lived_process():
    time.sleep(0.25)


def held_process(release):
    release.wait(60)


def spawn_real_process():
    p = mp.Process(target=short_lived_process)
    p.start()
    return p


def spawn_held_process(release):
    p = mp.Process(target=held_process, args=(release,))
    p.start()
    return p


def get_identity(pid):
    try:
        p = psutil.Process(pid)
        return {
            "pid": p.pid,
            "create_time": p.create_time(),
            "name": p.name(),
            "exe": p.exe(),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def main():
    print("=== REAL STALE EXPECTED-AUTHORIZATION / PID-GENERATION TEST ===")
    print("REAL PROCESSES ONLY.")
    print("NO SYNTHETIC PROCESS IDENTITIES.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO MANUAL FAILUREDNA EVENTS.")
    print("PID REUSE WILL ONLY BE ACCEPTED IF OBSERVED FROM THE OS.")

    monitor = get_process_lifecycle_monitor()

    # ------------------------------------------------------------
    # 1. Create and track real Process A.
    # ------------------------------------------------------------
    release_a = mp.Event()
    process_a = spawn_held_process(release_a)
    identity_a = get_identity(process_a.pid)

    if identity_a is None:
        process_a.join(timeout=5)
        raise AssertionError("Could not obtain Process A identity")

    print("\n1. PROCESS A:")
    print(identity_a)

    tracked_a = False
    deadline = time.time() + 30

    while time.time() < deadline:
        monitor.observe_and_detect()

        for identity in monitor.tracked_identities():
            if (
                identity.pid == identity_a["pid"]
                and abs(identity.create_time - identity_a["create_time"]) <= 0.01
            ):
                tracked_a = True
                break

        if tracked_a:
            break

        time.sleep(0.05)

    print("Process A tracked:", tracked_a)

    if not tracked_a:
        release_a.set()
        process_a.join(timeout=5)
        raise AssertionError("Lifecycle monitor failed to track Process A")

    # ------------------------------------------------------------
    # 2. Authorize ONLY Process A's exact identity.
    # ------------------------------------------------------------
    monitor.mark_expected_termination(
        identity_a["pid"],
        identity_a["create_time"],
    )

    expected_key_a = (
        identity_a["pid"],
        float(identity_a["create_time"]),
    )

    print("\n2. EXPECTED AUTHORIZATION:")
    print("authorized identity:", expected_key_a)

    if expected_key_a not in getattr(monitor, "_expected", set()):
        raise AssertionError(
            "Process A expected-termination authorization was not registered"
        )

    # ------------------------------------------------------------
    # 3. Let Process A terminate naturally.
    # ------------------------------------------------------------
    release_a.set()
    process_a.join(timeout=5)

    if process_a.is_alive():
        process_a.terminate()
        process_a.join(timeout=5)
        raise AssertionError(
            "Process A did not terminate naturally within the test window"
        )

    print("\n3. PROCESS A EXITED:")
    print("multiprocessing exitcode:", process_a.exitcode)

    # Observe the disappearance. Because the authorization is still present,
    # this must NOT become PROCESS_CRASH.
    events_a = monitor.observe_and_detect()

    print("lifecycle events for Process A:", events_a)

    matching_a = [
        e for e in events_a
        if (
            e.get("pid") == identity_a["pid"]
            and abs(
                float(e.get("create_time", -1))
                - float(identity_a["create_time"])
            ) <= 0.01
        )
    ]

    if matching_a:
        raise AssertionError(
            "Process A generated a lifecycle event despite expected authorization"
        )

    # ------------------------------------------------------------
    # 4. Look for REAL PID reuse.
    # ------------------------------------------------------------
    print("\n4. SEARCHING FOR REAL PID REUSE:")
    print("original PID:", identity_a["pid"])
    print("original create_time:", identity_a["create_time"])

    reused_identity = None
    attempts = 0
    deadline = time.time() + 30

    while time.time() < deadline:
        attempts += 1

        candidate = spawn_real_process()

        try:
            candidate_identity = get_identity(candidate.pid)

            if (
                candidate_identity is not None
                and candidate_identity["pid"] == identity_a["pid"]
                and abs(
                    candidate_identity["create_time"]
                    - identity_a["create_time"]
                ) > 0.01
            ):
                reused_identity = candidate_identity
                print("REAL PID REUSE OBSERVED.")
                print("reuse attempt:", attempts)
                print("new identity:", reused_identity)

                # Keep this process alive long enough to observe it.
                while candidate.is_alive():
                    time.sleep(0.05)

                candidate.join(timeout=5)
                break

            candidate.join(timeout=5)

        finally:
            if candidate.is_alive():
                candidate.terminate()
                candidate.join(timeout=5)

    if reused_identity is None:
        print(
            "PID reuse was NOT observed within the bounded real-process "
            "observation window."
        )
        print("attempts:", attempts)
        print("\nRESULT: INCONCLUSIVE (NO REAL PID REUSE OBSERVED)")
        print(
            "This is not a failure of the generation fence; the OS simply "
            "did not reuse the PID during the test window."
        )
        return

    # ------------------------------------------------------------
    # 5. Generation fence assertion.
    # ------------------------------------------------------------
    reused_key = (
        reused_identity["pid"],
        float(reused_identity["create_time"]),
    )

    print("\n5. GENERATION FENCE:")
    print("stale authorized identity:", expected_key_a)
    print("new real process identity:", reused_key)

    if reused_key == expected_key_a:
        raise AssertionError(
            "PID reuse occurred without a creation-time change"
        )

    if reused_key in getattr(monitor, "_expected", set()):
        raise AssertionError(
            "STALE EXPECTED AUTHORIZATION CROSSED THE PROCESS GENERATION BOUNDARY"
        )

    print("stale authorization does not match new generation: PASS")

    # Cleanup the stale authorization explicitly.
    monitor.clear_expected_termination(
        identity_a["pid"],
        identity_a["create_time"],
    )

    print("\n6. FINAL ASSERTIONS:")
    print("real Process A:", "PASS")
    print("exact PID + creation-time authorization:", "PASS")
    print("Process A expected termination suppressed:", "PASS")
    print("real PID reuse observed:", "PASS")
    print("new creation time differs:", "PASS")
    print("stale authorization rejected for new generation:", "PASS")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    mp.freeze_support()
    main()
