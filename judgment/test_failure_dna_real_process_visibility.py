import asyncio
import multiprocessing as mp
import os
import time

import psutil

from backend.main import app


def real_cpu_process():
    print(f"REAL CHILD STARTED: PID={os.getpid()}", flush=True)

    # Real CPU workload so the production endpoint's top-10 CPU
    # ranking has a strong chance of including this process.
    value = 0
    while True:
        value = (value + 1) % 1000000007


async def call_production_process_route():
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

    result = route.endpoint()

    if hasattr(result, "__await__"):
        result = await result

    return result


def find_pid_in_response(response, pid):
    if not isinstance(response, dict):
        return None

    matches = []

    for key in ("by_cpu", "by_mem"):
        records = response.get(key, [])

        if not isinstance(records, list):
            continue

        for record in records:
            if isinstance(record, dict) and record.get("pid") == pid:
                matches.append((key, record))

    return matches


async def run():
    print("=== REAL PRODUCTION PROCESS VISIBILITY VERIFICATION ===")
    print()
    print("READ-ONLY PRODUCTION VERIFICATION.")
    print("No synthetic telemetry.")
    print("No manual FailureDNA event.")
    print("No prediction creation.")
    print("No remediation.")
    print()

    ctx = mp.get_context("spawn")
    child = ctx.Process(target=real_cpu_process)

    child.start()
    pid = child.pid

    print(f"REAL CHILD PID: {pid}")

    try:
        assert pid is not None

        # ---------------------------------------------------------
        # 1. DIRECT REAL-WORLD PROCESS OBSERVATION
        # ---------------------------------------------------------
        observed_directly = False

        for attempt in range(10):
            try:
                proc = psutil.Process(pid)

                if proc.is_running():
                    observed_directly = True

                    name = proc.name()
                    status = proc.status()

                    # Establish a real CPU measurement.
                    proc.cpu_percent(interval=0.25)

                    print()
                    print("1. DIRECT PSUTIL OBSERVATION")
                    print("   PID:", pid)
                    print("   name:", name)
                    print("   status:", status)
                    print("   running:", proc.is_running())
                    print("PASS: Real child is visible through psutil.")

                    break

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            await asyncio.sleep(0.5)

        assert observed_directly, (
            "Direct psutil observation never saw the real child process."
        )

        # Give the process CPU time so its CPU ranking is meaningful.
        await asyncio.sleep(1.0)

        # ---------------------------------------------------------
        # 2. ACTUAL PRODUCTION /os/processes
        # ---------------------------------------------------------
        response = await call_production_process_route()

        print()
        print("2. PRODUCTION /os/processes RESPONSE")

        if not isinstance(response, dict):
            print("   response type:", type(response).__name__)
            print("   response:", response)
        else:
            by_cpu = response.get("by_cpu", [])
            by_mem = response.get("by_mem", [])

            print("   by_cpu records:", len(by_cpu))
            print("   by_mem records:", len(by_mem))

            matches = find_pid_in_response(response, pid)

            if matches:
                for source, record in matches:
                    print()
                    print(f"   MATCH FOUND IN {source}:")
                    print("   ", record)
            else:
                print()
                print("   NO MATCH FOR REAL CHILD PID.")
                print("   PID searched:", pid)

                print()
                print("   Top CPU PIDs:")
                for record in by_cpu[:10]:
                    print("   ", record)

                print()
                print("   Top memory PIDs:")
                for record in by_mem[:10]:
                    print("   ", record)

        matches = find_pid_in_response(response, pid)

        # ---------------------------------------------------------
        # 3. CORRELATION RESULT
        # ---------------------------------------------------------
        print()
        print("3. VISIBILITY CORRELATION")

        if matches:
            print("PASS: Production /os/processes exposes the real child PID.")
            print("PASS: Direct psutil observation and production process view agree.")
        else:
            print("FAIL: Direct psutil sees the real child, but production")
            print("/os/processes does not expose the same PID.")
            print()
            print("This is an actual production process-visibility gap.")
            raise AssertionError(
                "Production /os/processes failed to expose a directly observed real PID."
            )

    finally:
        # ---------------------------------------------------------
        # 4. REAL CHILD CLEANUP
        # ---------------------------------------------------------
        if child.is_alive():
            child.terminate()

        child.join(timeout=5)

        if child.is_alive():
            child.kill()
            child.join(timeout=5)

        print()
        print("4. REAL CHILD CLEANUP")
        print("   exitcode:", child.exitcode)

        assert child.exitcode is not None


if __name__ == "__main__":
    mp.freeze_support()
    asyncio.run(run())
