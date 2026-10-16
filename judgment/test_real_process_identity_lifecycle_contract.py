import multiprocessing as mp
import os
import time
import psutil


def real_child():
    while True:
        time.sleep(0.2)


def identity(pid):
    proc = psutil.Process(pid)
    return {
        "pid": proc.pid,
        "create_time": proc.create_time(),
        "name": proc.name(),
        "exe": proc.exe(),
        "ppid": proc.ppid(),
    }


def same_identity(a, b):
    return (
        a["pid"] == b["pid"]
        and abs(float(a["create_time"]) - float(b["create_time"])) <= 0.01
        and a["name"].lower() == b["name"].lower()
    )


def main():
    print("=== REAL PROCESS IDENTITY / LIFECYCLE CONTRACT TEST ===")
    print("REAL PROCESSES ONLY.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO FailureDNA EVENT.")
    print("NO PRODUCTION STATE MODIFICATION.")

    print("\n1. STARTING REAL PROCESS")

    child = mp.Process(target=real_child)
    child.start()

    pid = child.pid
    assert pid is not None

    first = identity(pid)

    print("   PID:", first["pid"])
    print("   create_time:", first["create_time"])
    print("   name:", first["name"])
    print("   exe:", first["exe"])
    print("   ppid:", first["ppid"])

    print("PASS")

    print("\n2. RE-OBSERVING SAME PROCESS")

    observations = []

    for i in range(4):
        time.sleep(0.5)

        current = identity(pid)
        observations.append(current)

        print(
            f"   observation {i + 1}: "
            f"pid={current['pid']} "
            f"create_time={current['create_time']} "
            f"status={psutil.Process(pid).status()}"
        )

        assert same_identity(first, current)

    print("PASS: Process identity remained stable.")

    print("\n3. TERMINATING REAL PROCESS")

    proc = psutil.Process(pid)
    proc.terminate()
    child.join(timeout=5)

    print("   exitcode:", child.exitcode)

    assert child.exitcode is not None

    try:
        psutil.Process(pid)
        still_exists = True
    except psutil.NoSuchProcess:
        still_exists = False

    assert not still_exists

    print("PASS: Original process disappeared.")

    print("\n4. STARTING SECOND REAL PROCESS")

    child2 = mp.Process(target=real_child)
    child2.start()

    pid2 = child2.pid
    assert pid2 is not None

    second = identity(pid2)

    print("   PID:", second["pid"])
    print("   create_time:", second["create_time"])
    print("   name:", second["name"])
    print("   exe:", second["exe"])

    print("\n5. PID / CREATION-TIME IDENTITY CHECK")

    print("   Original identity:")
    print("      PID:", first["pid"])
    print("      create_time:", first["create_time"])

    print("   New identity:")
    print("      PID:", second["pid"])
    print("      create_time:", second["create_time"])

    assert not same_identity(first, second)

    print("PASS: New process cannot be confused with original identity.")

    print("\n6. ORIGINAL IDENTITY MUST REMAIN ABSENT")

    try:
        old_proc = psutil.Process(first["pid"])
        old_identity = identity(first["pid"])

        if same_identity(first, old_identity):
            raise AssertionError(
                "Original process identity unexpectedly still exists."
            )

        print("INFO: PID was reused by a different identity.")
    except psutil.NoSuchProcess:
        print("PASS: Original PID remains absent.")

    print("\n7. CLEANUP")

    try:
        psutil.Process(pid2).terminate()
    except psutil.NoSuchProcess:
        pass

    child2.join(timeout=5)

    print("   second exitcode:", child2.exitcode)

    print("\n=== RESULT ===")
    print("PASS: Real process lifecycle identity contract established.")


if __name__ == "__main__":
    mp.freeze_support()
    main()
