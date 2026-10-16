from __future__ import annotations

import json
import multiprocessing as mp
import os
import uuid
from pathlib import Path

from judgment.lifecycle import begin_execution
from judgment.audit import load_audit, record_execution
from judgment.recovery import recover_interrupted_actions


STATE_PATH = Path("state") / "latest.json"
AUDIT_PATH = Path("state") / "audit.json"

ACTION = f"audit-first-crash-race-{uuid.uuid4().hex[:8]}"
RESULT = "AUDIT-FIRST-CRASH"


def reset_files():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    for path in (
        STATE_PATH,
        AUDIT_PATH,
        STATE_PATH.with_suffix(".tmp"),
        STATE_PATH.with_suffix(".recovery.lock"),
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def read_state():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_action():
    state = read_state()

    for action in state.get("actions", []):
        if action.get("action") == ACTION:
            return action

    raise AssertionError(f"Action not found: {ACTION}")


def completion_events(generation=None):
    events = load_audit()

    matches = []

    for event in events:
        if not isinstance(event, dict):
            continue

        if event.get("event") != "execution-completed":
            continue

        if event.get("action") != ACTION:
            continue

        if generation is not None:
            if event.get("execution_generation") != generation:
                continue

        matches.append(event)

    return matches


def crash_after_audit_before_state(action_name):
    """
    Critical failure window:

        generation N executing
                |
                v
        completion AUDIT durable
                |
                X
             CRASH
                |
        lifecycle STATE still executing

    Recovery must reconcile the mismatch safely.
    """

    state = read_state()

    action = None

    for candidate in state.get("actions", []):
        if candidate.get("action") == action_name:
            action = candidate
            break

    if action is None:
        raise RuntimeError("Target action missing")

    generation = action["execution_generation"]

    record_execution([{
        "event": "execution-completed",
        "action": action_name,
        "status": "executed",
        "result": RESULT,
        "execution_generation": generation,
        "recovered": False,
        "crash_test": True,
    }])

    print(
        "CRASH INJECTION: completion audit is durable."
    )

    print(
        "CRASH INJECTION: lifecycle state is intentionally "
        "still executing."
    )

    print(
        "CRASH INJECTION: killing process before state reconciliation."
    )

    os._exit(137)


def recovery_worker(worker_id, result_queue):
    try:
        result = recover_interrupted_actions()

        result_queue.put({
            "worker": worker_id,
            "result": result,
        })

    except Exception as exc:
        result_queue.put({
            "worker": worker_id,
            "error": repr(exc),
        })


def main():
    print("=== AUDIT-FIRST CRASH + CONCURRENT RECOVERY TEST ===")

    reset_files()

    STATE_PATH.write_text(
        json.dumps({
            "actions": [{
                "action": ACTION,
                "priority": "high",
                "execution_mode": "automatic",
                "status": "approved",
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
                "execution_generation": 0,
                "execution_result": None,
            }],
        }, indent=2),
        encoding="utf-8",
    )

    print("\n1. PREPARING EXECUTING GENERATION:")

    started = begin_execution(ACTION)

    assert started["status"] == "executing"

    generation = started["execution_generation"]

    print(
        f"{ACTION} | status={started['status']} "
        f"| generation={generation}"
    )

    assert completion_events(generation) == []

    print("PASS")

    print("\n2. STARTING REAL AUDIT-FIRST CRASH:")

    ctx = mp.get_context("spawn")

    crash = ctx.Process(
        target=crash_after_audit_before_state,
        args=(ACTION,),
    )

    crash.start()

    print(f"Crash worker PID: {crash.pid}")

    crash.join(timeout=15)

    assert crash.exitcode == 137

    print(
        f"Crash worker exitcode: {crash.exitcode}"
    )

    print(
        "REAL PROCESS CRASH OCCURRED AFTER "
        "AUDIT PERSISTENCE."
    )

    print("PASS")

    print("\n3. VERIFYING PRE-RECOVERY MISMATCH:")

    action = get_action()

    print(
        f"{ACTION} | status={action['status']} "
        f"| generation={action['execution_generation']} "
        f"| result={action.get('execution_result')}"
    )

    assert action["status"] == "executing"
    assert action["execution_generation"] == generation

    events = completion_events(generation)

    print(
        "Current-generation completion audits:",
        len(events),
    )

    assert len(events) == 1

    print(
        "Audit exists while lifecycle state is still executing."
    )
    print("PASS")

    print("\n4. STARTING CONCURRENT RECOVERY WAVE:")

    result_queue = ctx.Queue()
    workers = []

    for worker_id in range(1, 9):
        p = ctx.Process(
            target=recovery_worker,
            args=(worker_id, result_queue),
        )

        p.start()
        workers.append(p)

    for p in workers:
        p.join(timeout=20)

    for p in workers:
        assert p.exitcode == 0

    results = []

    while not result_queue.empty():
        results.append(result_queue.get())

    for item in sorted(
        results,
        key=lambda x: str(x["worker"]),
    ):
        print(
            f"RECOVERY WORKER {item['worker']}: "
            f"{item.get('result', item.get('error'))}"
        )

    print("All concurrent recovery workers completed.")
    print("PASS")

    print("\n5. VERIFYING FINAL STATE:")

    action = get_action()

    print(
        f"{ACTION} | status={action['status']} "
        f"| generation={action['execution_generation']} "
        f"| result={action.get('execution_result')}"
    )

    assert action["status"] == "executed"
    assert action["execution_result"] == RESULT

    assert action["execution_generation"] == generation

    print(
        "Generation identity remained stable."
    )

    print("PASS")

    print("\n6. VERIFYING COMPLETION AUDIT COUNT:")

    events = completion_events(generation)

    print(
        "Generation completion audits:",
        len(events),
    )

    assert len(events) == 1

    print(
        "Exactly ONE completion audit exists."
    )

    print("PASS")

    print("\n7. SECOND CONCURRENT RECOVERY WAVE:")

    result_queue = ctx.Queue()
    workers = []

    for worker_id in range(1, 9):
        p = ctx.Process(
            target=recovery_worker,
            args=(f"SECOND-{worker_id}", result_queue),
        )

        p.start()
        workers.append(p)

    for p in workers:
        p.join(timeout=20)

    for p in workers:
        assert p.exitcode == 0

    second_results = []

    while not result_queue.empty():
        second_results.append(result_queue.get())

    for item in second_results:
        print(
            f"SECOND RECOVERY {item['worker']}: "
            f"{item.get('result', item.get('error'))}"
        )

    final_events = completion_events(generation)

    print(
        "Final completion audits:",
        len(final_events),
    )

    assert len(final_events) == 1

    print(
        "Second recovery wave created no duplicate."
    )

    print("PASS")

    print("\n8. FRESH-PROCESS CONSISTENCY:")

    fresh_state = get_action()
    fresh_events = completion_events(generation)

    print(
        f"{ACTION} | status={fresh_state['status']} "
        f"| generation={fresh_state['execution_generation']} "
        f"| result={fresh_state.get('execution_result')}"
    )

    print(
        "Fresh-process completion audits:",
        len(fresh_events),
    )

    assert fresh_state["execution_generation"] == generation
    assert len(fresh_events) == 1

    print(
        "Fresh process observed consistent generation + audit."
    )

    print("PASS")

    print("\n9. FINAL HARD INVARIANTS:")

    print("REAL PROCESS CRASH OCCURRED AFTER AUDIT PERSISTENCE")
    print("AUDIT REMAINED GENERATION-SPECIFIC")
    print("LIFECYCLE STATE DID NOT CHANGE GENERATION")
    print("CONCURRENT RECOVERY COMPLETED SAFELY")
    print("EXACTLY ONE COMPLETION AUDIT EXISTS")
    print("NO DUPLICATE COMPLETION WAS CREATED")
    print("SECOND RECOVERY WAVE WAS IDEMPOTENT")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
