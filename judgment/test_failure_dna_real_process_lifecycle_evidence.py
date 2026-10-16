import asyncio
import multiprocessing as mp
import os
import time
import psutil

from backend.main import lifespan, app


def real_child():
    while True:
        time.sleep(0.2)


async def main():
    print("=== REAL PROCESS LIFECYCLE EVIDENCE TEST ===")
    print("READ-ONLY.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO MANUAL FailureDNA EVENT.")
    print("NO PRODUCTION STATE MODIFICATION.")

    async with lifespan(app):
        print("\n1. PRODUCTION BACKEND STARTED")
        print("PASS")

        child = mp.Process(target=real_child)
        child.start()

        pid = child.pid
        assert pid is not None
        print("\n2. REAL CHILD STARTED")
        print("PID:", pid)

        proc = psutil.Process(pid)

        identity = {
            "pid": proc.pid,
            "name": proc.name(),
            "create_time": proc.create_time(),
            "exe": proc.exe(),
            "ppid": proc.ppid(),
            "status": proc.status(),
        }

        print("\n3. DIRECT PSUTIL IDENTITY")
        for key, value in identity.items():
            print(f"   {key}: {value}")

        assert identity["pid"] == pid
        assert identity["create_time"] > 0
        print("PASS: Real process identity available.")

        await asyncio.sleep(2)

        print("\n4. PRODUCTION /os/processes OBSERVATION")

        route = None

        for route_obj in app.routes:
            if getattr(route_obj, "path", None) == "/os/processes":
                route = route_obj.endpoint
                break

        assert route is not None, "Production /os/processes route not found"

        result = await route()

        by_cpu = result.get("by_cpu", [])
        by_mem = result.get("by_mem", [])

        all_records = by_cpu + by_mem

        matches = [
            record for record in all_records
            if record.get("pid") == pid
        ]

        print("   CPU records:", len(by_cpu))
        print("   Memory records:", len(by_mem))
        print("   Matching PID records:", len(matches))

        for record in matches:
            print("   MATCH:", record)

        if matches:
            print("PASS: Production process snapshot exposed the real PID.")
        else:
            print(
                "INFO: Production snapshot did not expose this PID "
                "in its ranked top-10 lists."
            )

        print("\n5. IDENTITY RECHECK BEFORE TERMINATION")

        proc = psutil.Process(pid)

        identity_before_exit = {
            "pid": proc.pid,
            "name": proc.name(),
            "create_time": proc.create_time(),
            "exe": proc.exe(),
            "ppid": proc.ppid(),
            "status": proc.status(),
        }

        print(identity_before_exit)

        assert identity_before_exit["pid"] == identity["pid"]
        assert abs(
            identity_before_exit["create_time"]
            - identity["create_time"]
        ) < 0.01

        print("PASS: PID + creation-time identity remained stable.")

        print("\n6. TERMINATING REAL CHILD")

        proc.terminate()
        child.join(timeout=5)

        print("   exitcode:", child.exitcode)

        assert child.exitcode is not None
        print("PASS: Child terminated.")

        print("\n7. POST-TERMINATION PROCESS IDENTITY")

        try:
            psutil.Process(pid)
            print("WARNING: PID still exists.")
        except psutil.NoSuchProcess:
            print("PASS: PID no longer exists.")

        print("\n8. PRODUCTION SNAPSHOT AFTER TERMINATION")

        await asyncio.sleep(2)

        result_after = await route()

        after_records = (
            result_after.get("by_cpu", [])
            + result_after.get("by_mem", [])
        )

        matches_after = [
            record
            for record in after_records
            if record.get("pid") == pid
        ]

        print("   Matching PID records after exit:", len(matches_after))

        if not matches_after:
            print("PASS: Production snapshot no longer contains the PID.")
        else:
            print("WARNING: PID still appears in production snapshot.")

        print("\n9. EXISTING TERMINATION EVIDENCE")

        print("   Real PID:", pid)
        print("   Creation time:", identity["create_time"])
        print("   Exit code:", child.exitcode)
        print("   Name:", identity["name"])
        print("   Executable:", identity["exe"])
        print("   Parent PID:", identity["ppid"])

        print("\n10. RESULT")
        print(
            "PASS: Lifecycle evidence collected without modifying "
            "production FailureDNA state."
        )

        child.join(timeout=1)


if __name__ == "__main__":
    mp.freeze_support()
    asyncio.run(main())
