from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

from judgment.audit import load_audit
from judgment.lifecycle import begin_execution, complete_execution


STATE_PATH = Path("state") / "latest.json"
ACTION = "free-disk-space"


def load_state():
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def get_action():
    state = load_state()
    return next(
        a for a in state["actions"]
        if a.get("action") == ACTION
    )


def prepare_state():
    state = load_state()

    target = next(
        (
            action
            for action in state["actions"]
            if action.get("action") == ACTION
        ),
        None,
    )

    if target is None:
        target = {
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
        }
        state.setdefault("actions", []).append(target)

    target["status"] = "approved"
    target["retry_count"] = 0
    target["max_retries"] = 2
    target["escalation_required"] = False
    target["execution_result"] = None

    target.pop("execution_completed_at", None)
    target.pop("execution_started_at", None)

    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def completion_worker(
    worker_id: int,
    generation: int,
    crash: bool,
):
    """
    Each process independently attempts to complete the SAME
    execution generation.

    Worker 1 deliberately dies after reaching the completion call.
    """

    result = complete_execution(
        ACTION,
        success=True,
        result=f"CRASH-RACE-WORKER-{worker_id}",
        execution_generation=generation,
    )

    print(
        f"WORKER {worker_id}: {result}",
        flush=True,
    )

    if crash:
        os._exit(137)


def main():
    multiprocessing.freeze_support()

    print()
    print("=== CRASH DURING CONCURRENT COMPLETION TEST ===")
    print()

    # ------------------------------------------------------------
    # 1. PREPARE CLEAN APPROVED STATE
    # ------------------------------------------------------------
    print("1. PREPARING CLEAN APPROVED STATE:")

    prepare_state()

    action = get_action()

    print(
        ACTION,
        "| status =", action["status"],
        "| retry_count =", action["retry_count"],
    )

    assert action["status"] == "approved"
    assert action["retry_count"] == 0

    print("PASS")

    # ------------------------------------------------------------
    # 2. START EXECUTION
    # ------------------------------------------------------------
    print()
    print("2. STARTING EXECUTION:")

    before = load_audit()

    started = begin_execution(ACTION)

    print("START:", started)

    assert started["status"] == "executing"

    generation = started["execution_generation"]

    print("Execution generation:", generation)
    print("PASS")

    # ------------------------------------------------------------
    # 3. VERIFY DURABLE EXECUTING STATE
    # ------------------------------------------------------------
    print()
    print("3. VERIFYING DURABLE EXECUTING STATE:")

    action = get_action()

    print(
        ACTION,
        "| status =", action["status"],
        "| generation =", action.get("execution_generation"),
    )

    assert action["status"] == "executing"
    assert action["execution_generation"] == generation

    print("PASS")

    # ------------------------------------------------------------
    # 4. CONCURRENT COMPLETION PROCESSES
    # ------------------------------------------------------------
    print()
    print("4. CONCURRENT COMPLETION + REAL PROCESS CRASH:")

    processes = []

    for worker_id in range(1, 9):
        process = multiprocessing.Process(
            target=completion_worker,
            args=(
                worker_id,
                generation,
                worker_id == 1,
            ),
        )

        processes.append(process)

    for process in processes:
        process.start()

    for process in processes:
        process.join()

    print()
    print("PROCESS EXIT CODES:")

    for worker_id, process in enumerate(processes, start=1):
        print(
            f"Worker {worker_id}: "
            f"PID={process.pid} "
            f"exitcode={process.exitcode}"
        )

    crashed = [
        process
        for process in processes
        if process.exitcode == 137
    ]

    assert len(crashed) == 1

    print()
    print("Exactly one worker experienced a real process crash.")
    print("PASS")

    # ------------------------------------------------------------
    # 5. DURABLE STATE AFTER CRASH RACE
    # ------------------------------------------------------------
    print()
    print("5. DURABLE STATE AFTER CRASH RACE:")

    action = get_action()

    print(
        ACTION,
        "| status =", action["status"],
        "| result =", action.get("execution_result"),
        "| generation =", action.get("execution_generation"),
    )

    assert action["execution_generation"] == generation

    assert action["status"] in {
        "executed",
        "executing",
        "failed",
    }

    print("No impossible durable state detected.")
    print("PASS")

    # ------------------------------------------------------------
    # 6. AUDIT COMPLETION COUNT
    # ------------------------------------------------------------
    print()
    print("6. AUDIT:")

    after = load_audit()

    events = [
        event
        for event in after[len(before):]
        if event.get("action") == ACTION
    ]

    completion_events = [
        event
        for event in events
        if event.get("event") == "execution-completed"
    ]

    print("New action events:")

    for event in events:
        print(
            event.get("event"),
            "|",
            event.get("status"),
            "|",
            event.get("result"),
        )

    print()
    print(
        "execution-completed events:",
        len(completion_events),
    )

    assert len(completion_events) <= 1

    print("No duplicate durable completion events.")
    print("PASS")

    # ------------------------------------------------------------
    # 7. RECOVERY BOUNDARY
    # ------------------------------------------------------------
    print()
    print("7. FRESH-PROCESS RECOVERY CHECK:")

    recovery_code = """
from judgment.recovery import recover_interrupted_actions

result = recover_interrupted_actions()
print("RECOVERY RESULT:", result)
"""

    import subprocess
    import sys

    recovery = subprocess.run(
        [
            sys.executable,
            "-c",
            recovery_code,
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )

    print(recovery.stdout)

    if recovery.returncode != 0:
        print(recovery.stderr)
        raise SystemExit(recovery.returncode)

    print("Fresh-process recovery completed.")
    print("PASS")

    # ------------------------------------------------------------
    # 8. FINAL DURABLE STATE
    # ------------------------------------------------------------
    print()
    print("8. FINAL DURABLE STATE:")

    final_action = get_action()

    print(
        ACTION,
        "| status =", final_action["status"],
        "| result =", final_action.get("execution_result"),
        "| generation =", final_action.get(
            "execution_generation"
        ),
    )

    assert (
        final_action.get("execution_generation")
        == generation
    )

    assert final_action["status"] in {
        "executed",
        "failed",
    }

    print("PASS")

    # ------------------------------------------------------------
    # 9. FINAL AUDIT CONSISTENCY
    # ------------------------------------------------------------
    print()
    print("9. FINAL AUDIT CONSISTENCY:")

    final_audit = load_audit()

    final_events = [
        event
        for event in final_audit
        if (
            event.get("action") == ACTION
            and event.get("event") == "execution-completed"
            and event.get("result", "").startswith(
                "CRASH-RACE-WORKER-"
            )
        )
    ]

    print(
        "Crash-race completion events:",
        len(final_events),
    )

    for event in final_events:
        print(event)

    assert len(final_events) <= 1

    if final_action["status"] == "executed":
        assert len(final_events) == 1

        assert (
            final_action["execution_result"]
            == final_events[0]["result"]
        )

        print(
            "Executed state and audit agree on "
            "the winning completion."
        )

    else:
        print(
            "Execution did not become success; "
            "no false completion accepted."
        )

    print("PASS")

    # ------------------------------------------------------------
    # 10. FINAL INVARIANTS
    # ------------------------------------------------------------
    print()
    print("10. FINAL CRASH + CONCURRENCY INVARIANTS:")

    print("REAL PROCESS CRASH OCCURRED")
    print("EXECUTION GENERATION REMAINED STABLE")
    print("NO DUPLICATE COMPLETION WAS DURABLY RECORDED")
    print("NO IMPOSSIBLE DURABLE STATE EXISTED")
    print("FRESH-PROCESS RECOVERY COMPLETED")
    print("FINAL STATE AND AUDIT REMAINED CONSISTENT")

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
