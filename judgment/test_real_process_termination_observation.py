import multiprocessing as mp
import time
import psutil


def real_child():
    time.sleep(3)
    raise SystemExit(23)


def main():
    print("=== REAL PROCESS TERMINATION OBSERVATION TEST ===")
    print("REAL PROCESS.")
    print("REAL OS TERMINATION.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO FailureDNA.")
    print("NO PRODUCTION STATE CHANGES.")

    child = mp.Process(target=real_child)
    child.start()

    pid = child.pid
    assert pid is not None

    proc = psutil.Process(pid)

    print("\n1. PROCESS STARTED")
    print("   PID:", pid)
    print("   name:", proc.name())
    print("   create_time:", proc.create_time())
    print("   status:", proc.status())
    print("PASS")

    print("\n2. WAITING FOR REAL PROCESS TERMINATION")

    observed_exit = None

    while observed_exit is None:
        try:
            observed_exit = proc.wait(timeout=0.25)
        except psutil.TimeoutExpired:
            print("   still running")
        except psutil.NoSuchProcess:
            print("   process disappeared before wait returned")
            break

    print("\n3. TERMINATION OBSERVATION")
    print("   psutil wait result:", observed_exit)

    child.join(timeout=1)

    print("   multiprocessing exitcode:", child.exitcode)

    print("\n4. COMPARISON")

    if observed_exit is not None:
        print("PASS: psutil observed termination and returned an exit code.")
        print("   observed exit code:", observed_exit)
    else:
        print("FAIL: psutil did not return an exit code.")

    assert child.exitcode is not None

    print("\n5. RESULT")

    if observed_exit is not None:
        assert observed_exit == child.exitcode
        print(
            "PASS: Real process termination can be observed with "
            "an exact exit code."
        )
    else:
        raise AssertionError(
            "Production lifecycle design cannot rely on psutil.wait() "
            "without another termination mechanism."
        )


if __name__ == "__main__":
    mp.freeze_support()
    main()
