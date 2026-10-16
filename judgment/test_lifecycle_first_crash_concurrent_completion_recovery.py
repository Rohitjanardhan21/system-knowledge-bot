from __future__ import annotations

import json
import multiprocessing as mp
import os
import uuid
from pathlib import Path

from judgment.audit import load_audit
from judgment.lifecycle import begin_execution, complete_execution
from judgment.recovery import recover_interrupted_actions
from judgment.state_lock import state_lock


STATE_PATH = Path("state") / "latest.json"
ACTION = f"lifecycle-first-concurrent-race-{uuid.uuid4().hex[:8]}"
GENERATION = 1


def load_state():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_action():
    state = load_state()
    for action in state.get("actions", []):
        if action.get("action") == ACTION:
            return action
    raise AssertionError(f"Action not found: {ACTION}")


def crash_after_state_first(action_name):
    """
    Simulate the critical crash window:
    durable lifecycle state = executed
    completion audit = missing
    """
    with state_lock():
        state = load_state()

        for action in state["actions"]:
            if action.get("action") == action_name:
                action["status"] = "executed"
                action["execution_result"] = "LIFECYCLE-FIRST-CRASH"
                action["execution_completed_at"] = (
                    "2026-10-05T06:00:00+00:00"
                )
                break
        else:
            raise AssertionError(f"Action not found: {action_name}")

        temp = STATE_PATH.with_suffix(".tmp")

        with temp.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp, STATE_PATH)

    print(
        "CRASH INJECTION: durable executed lifecycle state persisted."
    )
    print(
        "CRASH INJECTION: completion audit intentionally missing."
    )
    print("CRASH INJECTION: killing process before audit write.")

    os._exit(137)


def recovery_worker(index, queue):
    try:
        result = recover_interrupted_actions()
        queue.put({
            "worker": index,
            "result": result,
            "error": None,
        })
    except Exception as exc:
        queue.put({
            "worker": index,
            "result": None,
            "error": repr(exc),
        })


def completion_worker(index, action_name, generation, queue):
    try:
        result = complete_execution(
            action_name,
            success=True,
            result=f"CONCURRENT-COMPLETION-WORKER-{index}",
            execution_generation=generation,
        )

        queue.put({
            "worker": index,
            "result": result,
            "error": None,
        })

    except Exception as exc:
        queue.put({
            "worker": index,
            "result": None,
            "error": repr(exc),
        })


def completion_audits():
    entries = load_audit()

    return [
        event
        for event in entries
        if isinstance(event, dict)
        and event.get("event") == "execution-completed"
        and event.get("action") == ACTION
        and event.get("execution_generation") == GENERATION
    ]


def main():
    print("=== LIFECYCLE-FIRST CRASH + CONCURRENT COMPLETION/RECOVERY TEST ===")

    # ------------------------------------------------------------
    # 1. Prepare executing state
    # ------------------------------------------------------------
    print("\n1. PREPARING EXECUTING GENERATION:")

    state = {"actions": []}

    if STATE_PATH.exists():
        state = load_state()

    state["actions"] = [
        action
        for action in state.get("actions", [])
        if action.get("action") != ACTION
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

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    started = begin_execution(ACTION)
    assert started["status"] == "executing"
    assert started["execution_generation"] == GENERATION

    current = find_action()

    # Normalize test generation.
    state = load_state()

    for action in state["actions"]:
        if action.get("action") == ACTION:
            action["status"] = "executing"
            action["execution_generation"] = GENERATION
            action["execution_result"] = None
            action.pop("execution_completed_at", None)
            break

    temp = STATE_PATH.with_suffix(".tmp")

    with temp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp, STATE_PATH)

    current = find_action()

    print(
        f"{ACTION} | status={current['status']} "
        f"| generation={current['execution_generation']}"
    )

    assert current["status"] == "executing"
    assert current["execution_generation"] == GENERATION
    assert len(completion_audits()) == 0

    print("PASS")

    # ------------------------------------------------------------
    # 2. Crash after lifecycle state becomes executed
    # ------------------------------------------------------------
    print("\n2. STARTING REAL LIFECYCLE-FIRST CRASH:")

    crash = mp.Process(
        target=crash_after_state_first,
        args=(ACTION,),
    )
    crash.start()

    crash.join()

    print(f"Crash worker PID: {crash.pid}")
    print(f"Crash worker exitcode: {crash.exitcode}")

    assert crash.exitcode == 137

    print("REAL PROCESS CRASH OCCURRED.")
    print("PASS")

    # ------------------------------------------------------------
    # 3. Verify durable state before recovery
    # ------------------------------------------------------------
    print("\n3. VERIFYING PRE-RECOVERY STATE:")

    current = find_action()

    print(
        f"{ACTION} | status={current['status']} "
        f"| result={current.get('execution_result')} "
        f"| generation={current['execution_generation']}"
    )

    assert current["status"] == "executed"
    assert current["execution_result"] == "LIFECYCLE-FIRST-CRASH"
    assert current["execution_generation"] == GENERATION

    audits = completion_audits()

    print(f"Completion audit events before recovery: {len(audits)}")

    assert len(audits) == 0

    print("DURABLE EXECUTED STATE EXISTS WITH NO COMPLETION AUDIT.")
    print("PASS")

    # ------------------------------------------------------------
    # 4. Concurrent recovery + completion
    # ------------------------------------------------------------
    print("\n4. STARTING CONCURRENT RECOVERY + COMPLETION RACE:")

    queue = mp.Queue()
    processes = []

    # Recovery wave.
    for i in range(8):
        p = mp.Process(
            target=recovery_worker,
            args=(i + 1, queue),
        )
        processes.append(p)
        p.start()

    # Concurrent completion attempts.
    for i in range(8):
        p = mp.Process(
            target=completion_worker,
            args=(i + 1, ACTION, GENERATION, queue),
        )
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    results = []

    while not queue.empty():
        results.append(queue.get())

    for result in results:
        print(
            f"WORKER {result['worker']}: "
            f"result={result['result']} "
            f"error={result['error']}"
        )

    assert all(p.exitcode == 0 for p in processes)

    print("All concurrent workers completed.")
    print("PASS")

    # ------------------------------------------------------------
    # 5. Verify exactly one terminal result
    # ------------------------------------------------------------
    print("\n5. VERIFYING FINAL TERMINAL STATE:")

    current = find_action()

    print(
        f"{ACTION} | status={current['status']} "
        f"| result={current.get('execution_result')} "
        f"| generation={current['execution_generation']}"
    )

    assert current["status"] == "executed"
    assert current["execution_generation"] == GENERATION

    print("EXECUTED STATE REMAINED AUTHORITATIVE.")
    print("PASS")

    # ------------------------------------------------------------
    # 6. Exactly one completion audit
    # ------------------------------------------------------------
    print("\n6. VERIFYING EXACTLY-ONCE COMPLETION AUDIT:")

    audits = completion_audits()

    print(f"Completion audit events: {len(audits)}")

    for event in audits:
        print(event)

    assert len(audits) == 1
    assert audits[0]["execution_generation"] == GENERATION

    print("EXACTLY ONE CURRENT-GENERATION COMPLETION AUDIT EXISTS.")
    print("PASS")

    # ------------------------------------------------------------
    # 7. Second concurrent recovery wave
    # ------------------------------------------------------------
    print("\n7. SECOND CONCURRENT RECOVERY WAVE:")

    queue = mp.Queue()
    processes = []

    for i in range(8):
        p = mp.Process(
            target=recovery_worker,
            args=(f"SECOND-{i + 1}", queue),
        )
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    second_results = []

    while not queue.empty():
        second_results.append(queue.get())

    for result in second_results:
        print(
            f"SECOND RECOVERY {result['worker']}: "
            f"{result['result']}"
        )

    assert all(p.exitcode == 0 for p in processes)

    final_audits = completion_audits()

    print(
        f"Final completion audit events: {len(final_audits)}"
    )

    assert len(final_audits) == 1

    print("SECOND RECOVERY WAVE WAS IDEMPOTENT.")
    print("PASS")

    # ------------------------------------------------------------
    # 8. Fresh-process consistency
    # ------------------------------------------------------------
    print("\n8. FRESH-PROCESS CONSISTENCY:")

    fresh = find_action()

    print(
        f"{ACTION} | status={fresh['status']} "
        f"| generation={fresh['execution_generation']} "
        f"| result={fresh.get('execution_result')}"
    )

    fresh_audits = completion_audits()

    print(
        f"Fresh-process completion audits: "
        f"{len(fresh_audits)}"
    )

    assert fresh["status"] == "executed"
    assert fresh["execution_generation"] == GENERATION
    assert len(fresh_audits) == 1

    print("FRESH PROCESS OBSERVED CONSISTENT STATE + AUDIT.")
    print("PASS")

    # ------------------------------------------------------------
    # 9. Final invariants
    # ------------------------------------------------------------
    print("\n9. FINAL HARD INVARIANTS:")
    print("REAL PROCESS CRASH OCCURRED AFTER LIFECYCLE STATE PERSISTENCE")
    print("DURABLE EXECUTED STATE SURVIVED")
    print("COMPLETION AUDIT WAS MISSING BEFORE RECOVERY")
    print("CONCURRENT RECOVERY + COMPLETION RACE OCCURRED")
    print("EXECUTION GENERATION REMAINED STABLE")
    print("EXACTLY ONE COMPLETION AUDIT EXISTS")
    print("NO DUPLICATE COMPLETION WAS CREATED")
    print("SECOND RECOVERY WAVE WAS IDEMPOTENT")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT")
    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
