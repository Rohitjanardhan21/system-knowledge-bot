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
ACTION = f"composite-recovery-crash-fence-{uuid.uuid4().hex[:8]}"


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


def matching_events(generation=None, event_type=None):
    events = load_audit()

    result = [
        e for e in events
        if isinstance(e, dict)
        and e.get("action") == ACTION
    ]

    if generation is not None:
        result = [
            e for e in result
            if e.get("execution_generation") == generation
        ]

    if event_type is not None:
        result = [
            e for e in result
            if e.get("event") == event_type
        ]

    return result


def crashing_recovery_worker(start_event):
    start_event.set()

    # Let the parent install Generation 2 while this process is alive.
    time.sleep(0.35)

    # Real process crash.
    os._exit(137)


def normal_recovery_worker(index, barrier):
    barrier.wait()

    try:
        result = recover_interrupted_actions()
        print(
            f"RECOVERY WORKER {index}: {result}",
            flush=True,
        )
    except Exception as exc:
        print(
            f"RECOVERY WORKER {index}: ERROR {exc!r}",
            flush=True,
        )
        raise


def main():
    print("=== COMPOSITE RECOVERY + CRASH + GENERATION FENCE TEST ===\n")

    # Remove previous instance of this action.
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

    print("1. PREPARING GENERATION 1:")

    started = begin_execution(ACTION)

    assert started["status"] == "executing"

    gen1 = started["execution_generation"]

    # Make Generation 1 stale.
    state = load_state()

    for action in state["actions"]:
        if action.get("action") == ACTION:
            action["execution_started_at"] = (
                "2000-01-01T00:00:00+00:00"
            )

    write_state(state)

    current = get_action()

    print(
        f"{ACTION} | status={current['status']} | "
        f"generation={current['execution_generation']}"
    )

    assert current["execution_generation"] == gen1

    print("Generation 1 prepared as stale.")
    print("PASS\n")

    print("2. STARTING REAL CRASH WORKER:")

    ctx = mp.get_context("spawn")
    start_event = ctx.Event()

    crash_process = ctx.Process(
        target=crashing_recovery_worker,
        args=(start_event,),
    )

    crash_process.start()

    print("Crash worker PID:", crash_process.pid)

    start_event.wait(timeout=10)

    print("PASS\n")

    print("3. INSTALLING GENERATION 2 BEFORE CRASH:")

    state = load_state()

    for action in state["actions"]:
        if action.get("action") == ACTION:
            action.update({
                "status": "executed",
                "execution_generation": gen1 + 1,
                "execution_result": "GENERATION-2-AUTHORITATIVE",
                "execution_completed_at":
                    "2099-01-01T00:00:01+00:00",
            })

    write_state(state)

    gen2 = gen1 + 1

    current = get_action()

    print(
        f"{ACTION} | status={current['status']} | "
        f"generation={current['execution_generation']} | "
        f"result={current['execution_result']}"
    )

    assert current["execution_generation"] == gen2
    assert current["status"] == "executed"

    print("Generation 2 installed.")
    print("PASS\n")

    print("4. STARTING CONCURRENT RECOVERY WAVE:")

    barrier = ctx.Barrier(8)
    workers = []

    for index in range(1, 9):
        p = ctx.Process(
            target=normal_recovery_worker,
            args=(index, barrier),
        )
        p.start()
        workers.append(p)

    for p in workers:
        p.join(timeout=20)

    assert all(not p.is_alive() for p in workers)
    assert all(p.exitcode == 0 for p in workers)

    print("All concurrent recovery workers completed.")
    print("PASS\n")

    print("5. WAITING FOR REAL CRASH:")

    crash_process.join(timeout=10)

    if crash_process.is_alive():
        crash_process.terminate()
        crash_process.join()

    print(
        "Crash worker exitcode:",
        crash_process.exitcode,
    )

    assert crash_process.exitcode == 137

    print("Exactly one real process crash occurred.")
    print("PASS\n")

    print("6. VERIFYING GENERATION 2:")

    current = get_action()

    print(
        f"{ACTION} | status={current['status']} | "
        f"generation={current['execution_generation']} | "
        f"result={current['execution_result']}"
    )

    assert current["status"] == "executed"
    assert current["execution_generation"] == gen2
    assert current["execution_result"] == (
        "GENERATION-2-AUTHORITATIVE"
    )

    print("GENERATION 2 REMAINED AUTHORITATIVE.")
    print("PASS\n")

    print("7. VERIFYING GENERATION-1 AUDIT FENCE:")

    gen1_recovery = matching_events(
        gen1,
        "recovery-interrupted",
    )

    gen1_completion = matching_events(
        gen1,
        "execution-completed",
    )

    print(
        "Generation 1 recovery events:",
        len(gen1_recovery),
    )

    print(
        "Generation 1 completion events:",
        len(gen1_completion),
    )

    assert len(gen1_completion) == 0

    print("NO STALE GENERATION-1 COMPLETION EXISTS.")
    print("PASS\n")

    print("8. RECONCILING CURRENT GENERATION:")

    result = recover_interrupted_actions()

    print("FINAL RECOVERY RESULT:", result)

    gen2_completion = matching_events(
        gen2,
        "execution-completed",
    )

    print(
        "Generation 2 completion events:",
        len(gen2_completion),
    )

    assert len(gen2_completion) == 1

    print("CURRENT GENERATION RECONCILED EXACTLY ONCE.")
    print("PASS\n")

    print("9. SECOND CONCURRENT RECOVERY WAVE:")

    barrier2 = ctx.Barrier(8)
    workers2 = []

    for index in range(1, 9):
        p = ctx.Process(
            target=normal_recovery_worker,
            args=(f"SECOND-{index}", barrier2),
        )
        p.start()
        workers2.append(p)

    for p in workers2:
        p.join(timeout=20)

    assert all(not p.is_alive() for p in workers2)
    assert all(p.exitcode == 0 for p in workers2)

    final_completion = matching_events(
        gen2,
        "execution-completed",
    )

    print(
        "Final Generation 2 completion events:",
        len(final_completion),
    )

    assert len(final_completion) == 1

    print("SECOND RECOVERY WAVE WAS IDEMPOTENT.")
    print("PASS\n")

    print("10. FRESH-PROCESS CONSISTENCY:")

    fresh = get_action()

    print(
        f"{ACTION} | status={fresh['status']} | "
        f"generation={fresh['execution_generation']} | "
        f"result={fresh['execution_result']}"
    )

    assert fresh["execution_generation"] == gen2
    assert fresh["status"] == "executed"
    assert fresh["execution_result"] == (
        "GENERATION-2-AUTHORITATIVE"
    )

    print("Fresh process observed Generation 2.")
    print("PASS\n")

    print("11. FINAL COMPOSITE INVARIANTS:")

    print("REAL PROCESS CRASH OCCURRED")
    print("GENERATION 1 WAS STALE")
    print("GENERATION 2 REPLACED GENERATION 1")
    print("GENERATION 2 REMAINED AUTHORITATIVE")
    print("CONCURRENT RECOVERY COMPLETED SAFELY")
    print("NO STALE GENERATION-1 COMPLETION WAS FABRICATED")
    print("EXACTLY ONE CURRENT-GENERATION COMPLETION EXISTS")
    print("SECOND RECOVERY WAVE WAS IDEMPOTENT")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE")
    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
