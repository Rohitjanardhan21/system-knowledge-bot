import asyncio
import multiprocessing as mp
import os
import time

import psutil

from backend.main import app


def real_cpu_process():
    print(f"REAL CHILD STARTED: PID={os.getpid()}", flush=True)

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


def find_record(response, pid):
    if not isinstance(response, dict):
        return []

    matches = []

    for source in ("by_cpu", "by_mem"):
        records = response.get(source, [])

        if not isinstance(records, list):
            continue

        for record in records:
            if isinstance(record, dict) and record.get("pid") == pid:
                matches.append((source, record))

    return matches


def get_production_pid_records(response, pid):
    matches = find_record(response, pid)
    return [record for _, record in matches]


async def production_sample(label, pid):
    response = await call_production_process_route()
    matches = find_record(response, pid)

    print()
    print(label)

    if matches:
        for source, record in matches:
            print(f"  {source}: {record}")
    else:
        print("  PID NOT PRESENT IN PRODUCTION VIEW")

    return response, matches


async def run():
    print("=== REAL PRODUCTION PROCESS CPU SAMPLING DIAGNOSTIC ===")
    print()
    print("REAL PROCESS ONLY.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO MANUAL FAILUREDNA EVENT.")
    print("NO PRODUCTION CODE MODIFICATION.")
    print()

    ctx = mp.get_context("spawn")
    child = ctx.Process(target=real_cpu_process)
    child.start()

    pid = child.pid
    assert pid is not None

    print(f"REAL CHILD PID: {pid}")

    proc = None

    try:
        # ---------------------------------------------------------
        # 1. ESTABLISH REAL PROCESS
        # ---------------------------------------------------------
        for _ in range(10):
            try:
                proc = psutil.Process(pid)

                if proc.is_running():
                    break

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            await asyncio.sleep(0.25)

        assert proc is not None
        assert proc.is_running()

        print()
        print("1. REAL PROCESS ESTABLISHED")
        print("  PID:", pid)
        print("  name:", proc.name())
        print("  status:", proc.status())

        # ---------------------------------------------------------
        # 2. DIRECT CPU MEASUREMENT BEFORE PRIMING
        # ---------------------------------------------------------
        direct_before = proc.cpu_percent(interval=1.0)

        print()
        print("2. DIRECT PSUTIL CPU MEASUREMENT")
        print("  cpu_percent(interval=1.0):", direct_before)

        assert direct_before > 0.0, (
            "The real CPU-intensive child did not produce a positive "
            "direct CPU measurement."
        )

        # ---------------------------------------------------------
        # 3. FIRST PRODUCTION SAMPLE
        # ---------------------------------------------------------
        response1, matches1 = await production_sample(
            "3. FIRST PRODUCTION /os/processes SAMPLE",
            pid,
        )

        # ---------------------------------------------------------
        # 4. PRIME THE EXACT PROCESS CPU COUNTER
        # ---------------------------------------------------------
        print()
        print("4. PRIMING DIRECT PROCESS CPU COUNTER")

        proc.cpu_percent(interval=None)

        await asyncio.sleep(1.0)

        direct_after_prime = proc.cpu_percent(interval=None)

        print(
            "  direct cpu_percent() after 1-second interval:",
            direct_after_prime,
        )

        # ---------------------------------------------------------
        # 5. SECOND PRODUCTION SAMPLE
        # ---------------------------------------------------------
        response2, matches2 = await production_sample(
            "5. SECOND PRODUCTION /os/processes SAMPLE AFTER PRIMING",
            pid,
        )

        # ---------------------------------------------------------
        # 6. REPEATED PRODUCTION SAMPLES
        # ---------------------------------------------------------
        print()
        print("6. REPEATED PRODUCTION SAMPLES")

        repeated = []

        for i in range(5):
            await asyncio.sleep(0.5)

            response = await call_production_process_route()
            records = get_production_pid_records(response, pid)

            cpu_values = [
                record.get("cpu")
                for record in records
                if isinstance(record.get("cpu"), (int, float))
            ]

            repeated.append(cpu_values)

            print(
                f"  sample {i + 1}:",
                cpu_values if cpu_values else "PID NOT PRESENT",
            )

        # ---------------------------------------------------------
        # 7. DIAGNOSIS
        # ---------------------------------------------------------
        print()
        print("7. DIAGNOSTIC RESULT")

        first_present = bool(matches1)
        second_present = bool(matches2)
        repeated_present = any(bool(values) for values in repeated)

        first_cpu = [
            record.get("cpu")
            for _, record in matches1
            if isinstance(record.get("cpu"), (int, float))
        ]

        second_cpu = [
            record.get("cpu")
            for _, record in matches2
            if isinstance(record.get("cpu"), (int, float))
        ]

        print("  direct CPU before production sampling:", direct_before)
        print("  production first PID visible:", first_present)
        print("  production second PID visible:", second_present)
        print("  production repeated PID visible:", repeated_present)
        print("  production first CPU:", first_cpu)
        print("  production second CPU:", second_cpu)

        if repeated_present:
            print()
            print(
                "RESULT: Production process enumeration eventually "
                "exposes the real PID."
            )
            print(
                "The remaining question is whether CPU sampling is "
                "incorrect/zero-valued or whether ranking is responsible."
            )

        elif not first_present and not second_present:
            print()
            print(
                "RESULT: Production endpoint still cannot expose the "
                "real PID despite direct psutil observation."
            )
            print(
                "This is stronger evidence of a production process-view "
                "enumeration/ranking problem rather than merely CPU priming."
            )

        else:
            print()
            print(
                "RESULT: Production visibility changed after CPU priming."
            )
            print(
                "This strongly implicates psutil CPU sampling/priming."
            )

        # ---------------------------------------------------------
        # 8. NO FAILUREDNA ASSERTION
        # ---------------------------------------------------------
        print()
        print("8. SCOPE")
        print("  This test does not create or modify FailureDNA events.")
        print("  This test does not create predictions.")
        print("  This test does not execute remediation.")

    finally:
        if child.is_alive():
            child.terminate()

        child.join(timeout=5)

        if child.is_alive():
            child.kill()
            child.join(timeout=5)

        print()
        print("9. REAL CHILD CLEANUP")
        print("  exitcode:", child.exitcode)

        assert child.exitcode is not None


if __name__ == "__main__":
    mp.freeze_support()
    asyncio.run(run())
