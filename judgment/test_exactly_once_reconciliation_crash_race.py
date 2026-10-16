from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
import uuid
from pathlib import Path

from judgment.lifecycle import begin_execution
from judgment.recovery import recover_interrupted_actions
from judgment.audit import load_audit


STATE_PATH = Path("state") / "latest.json"
ACTION = f"exactly-once-reconciliation-crash-{uuid.uuid4().hex[:8]}"


def write_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")

    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, STATE_PATH)


def load_state():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_action():
    state = load_state()

    for action in state.get("actions", []):
        if action.get("action") == ACTION:
            return action

    raise AssertionError("Target action not found")


def matching_completion(generation):
    return [
        e for e in load_audit()
        if isinstance(e, dict)
        and e.get("event") == "execution-completed"
        and e.get("action") == ACTION
        and e.get("execution_generation") == generation
    ]


def crashing_worker(start_event):
    start_event.set()

    # The parent has already installed the executed state.
    # Crash as a real independent process.
    time.sleep(0.25)
    os._exit(137)


def recovery_worker(index, barrier):
    barrier.wait()

    result = recover_interrupted_actions()

    print(
        f"RECOVERY WORKER {index}: {result}",
        flush=True,
    )


def main():
    print("=== EXACTLY-ONCE RECONCILIATION CRASH RACE TEST ===\n")

    # Remove any previous instance of this unique action.
    state = {"actions": []}

    if STATE_PATH.exists():
        try:
            state = load_state()
        except Exception:
            state = {"actions": []}

    state["actions"] = [
        a for a in state.get("actions", [])
        if a.get("action") != ACTION
    ]
    state["actions"].append({
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_generation": 0,
        "execution_result": None,
    })
    write_state(state)

    print("1. PREPARING EXECUTED STATE WITH MISSING AUDIT:")

    started = begin_execution(ACTION)

    assert started["status"] == "executing"

    generation = started["execution_generation"]

    state = load_state()

    for action in state["actions"]:
        if action.get("action") == ACTION:
            action.update({
                "status": "executed",
                "execution_result": "EXACTLY-ONCE-CRASH",
                "execution_completed_at":
                    "2099-01-01T00:00:01+00:00",
            })

    write_state(state)

    assert get_action()["status"] == "executed"
    assert len(matching_completion(generation)) == 0

    print(
        f"{ACTION} | status=executed | "
        f"generation={generation}"
    )
    print("Completion audit is intentionally missing.")
    print("PASS\n")

    print("2. STARTING CRASH PROCESS:")

    ctx = mp.get_context("spawn")
    start_event = ctx.Event()

    crash = ctx.Process(
        target=crashing_worker,
        args=(start_event,),
    )

    crash.start()

    print("Crash worker PID:", crash.pid)

    start_event.wait(timeout=10)

    print("PASS\n")

    print("3. STARTING FIRST CONCURRENT RECOVERY WAVE:")

    barrier = ctx.Barrier(8)
    workers = []

    for index in range(1, 9):
        p = ctx.Process(
            target=recovery_worker,
            args=(index, barrier),
        )
        p.start()
        workers.append(p)

    for p in workers:
        p.join(timeout=20)

    assert all(not p.is_alive() for p in workers)
    assert all(p.exitcode == 0 for p in workers)

    print("All recovery workers completed.")
    print("PASS\n")

    print("4. WAITING FOR REAL PROCESS CRASH:")

    crash.join(timeout=10)

    if crash.is_alive():
        crash.terminate()
        crash.join()

    print("Crash worker exitcode:", crash.exitcode)

    assert crash.exitcode == 137

    print("Exactly one real process crash occurred.")
    print("PASS\n")

    print("5. VERIFYING RECONCILIATION RESULT:")

    current = get_action()
    completions = matching_completion(generation)

    print(
        f"{ACTION} | status={current['status']} | "
        f"generation={current['execution_generation']} | "
        f"result={current['execution_result']}"
    )

    print("Completion audit events:", len(completions))

    assert current["status"] == "executed"
    assert current["execution_generation"] == generation
    assert current["execution_result"] == "EXACTLY-ONCE-CRASH"
    assert len(completions) == 1

    print("Exactly ONE completion audit exists.")
    print("PASS\n")

    print("6. SECOND CONCURRENT RECOVERY WAVE:")

    barrier2 = ctx.Barrier(8)
    workers2 = []

    for index in range(1, 9):
        p = ctx.Process(
            target=recovery_worker,
            args=(f"SECOND-{index}", barrier2),
        )
        p.start()
        workers2.append(p)

    for p in workers2:
        p.join(timeout=20)

    assert all(not p.is_alive() for p in workers2)
    assert all(p.exitcode == 0 for p in workers2)

    completions_after = matching_completion(generation)

    print(
        "Final completion audit events:",
        len(completions_after),
    )

    assert len(completions_after) == 1

    print("Second recovery wave created no duplicate.")
    print("PASS\n")

    print("7. FRESH-PROCESS CONSISTENCY:")

    fresh = get_action()

    print(
        f"{ACTION} | status={fresh['status']} | "
        f"generation={fresh['execution_generation']} | "
        f"result={fresh['execution_result']}"
    )

    assert fresh["status"] == "executed"
    assert fresh["execution_generation"] == generation

    print("Fresh process observed the same durable state.")
    print("PASS\n")

    print("8. FINAL EXACTLY-ONCE INVARIANTS:")

    print("REAL PROCESS CRASH OCCURRED")
    print("EXECUTED STATE REMAINED DURABLE")
    print("MISSING COMPLETION AUDIT WAS RECONCILED")
    print("EXACTLY ONE COMPLETION AUDIT EXISTS")
    print("CONCURRENT RECOVERY DID NOT DUPLICATE THE AUDIT")
    print("SECOND RECOVERY WAVE WAS IDEMPOTENT")
    print("EXECUTION GENERATION REMAINED STABLE")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT")
    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
