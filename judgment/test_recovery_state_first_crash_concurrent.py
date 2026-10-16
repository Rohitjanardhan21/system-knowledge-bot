from __future__ import annotations

import json
import multiprocessing as mp
import os
import uuid
from pathlib import Path

from judgment.audit import load_audit, record_execution
from judgment.recovery import recover_interrupted_actions
from judgment.state_lock import state_lock


STATE_PATH = Path("state") / "latest.json"
ACTION = f"recovery-state-first-crash-{uuid.uuid4().hex[:8]}"
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


def completion_events():
    return [
        event
        for event in load_audit()
        if isinstance(event, dict)
        and event.get("event") == "execution-completed"
        and event.get("action") == ACTION
        and event.get("execution_generation") == GENERATION
    ]


def recovery_events():
    return [
        event
        for event in load_audit()
        if isinstance(event, dict)
        and event.get("event") == "recovery-interrupted"
        and event.get("action") == ACTION
    ]


def prepare_executing_state():
    with state_lock():
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
            "status": "executing",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": None,
            "execution_generation": GENERATION,
            "execution_started_at": "2026-10-05T06:00:00+00:00",
        })

        temp = STATE_PATH.with_suffix(".tmp")

        with temp.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp, STATE_PATH)


def crash_after_recovery_state(action_name):
    """
    Simulate the critical recovery crash window.

    The lifecycle state is durably changed from executing -> failed,
    but the recovery audit is intentionally NOT written.
    """

    with state_lock():
        state = load_state()

        found = False

        for action in state.get("actions", []):
            if action.get("action") != action_name:
                continue

            assert action["status"] == "executing"

            action["status"] = "failed"
            action["execution_result"] = "interrupted-by-restart"
            action["execution_completed_at"] = (
                "2026-10-05T06:00:01+00:00"
            )
            action["recovery_reason"] = "interrupted-by-restart"

            found = True
            break

        assert found

        temp = STATE_PATH.with_suffix(".tmp")

        with temp.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp, STATE_PATH)

    print(
        "CRASH INJECTION: recovery state FAILED was durably persisted."
    )
    print(
        "CRASH INJECTION: recovery audit intentionally missing."
    )
    print(
        "CRASH INJECTION: killing process before recovery audit."
    )

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


def main():
    print("=== RECOVERY STATE-FIRST CRASH + CONCURRENT RECOVERY TEST ===")

    # ------------------------------------------------------------
    # 1. Prepare executing state
    # ------------------------------------------------------------
    print("\n1. PREPARING EXECUTING STATE:")

    prepare_executing_state()

    action = find_action()

    print(
        f"{ACTION} | status={action['status']} "
        f"| generation={action['execution_generation']}"
    )

    assert action["status"] == "executing"
    assert action["execution_generation"] == GENERATION

    assert len(recovery_events()) == 0
    assert len(completion_events()) == 0

    print("PASS")

    # ------------------------------------------------------------
    # 2. Real crash after recovery state persistence
    # ------------------------------------------------------------
    print("\n2. STARTING REAL RECOVERY-STATE-FIRST CRASH:")

    crash = mp.Process(
        target=crash_after_recovery_state,
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
    # 3. Verify durable failed state
    # ------------------------------------------------------------
    print("\n3. VERIFYING DURABLE FAILED STATE:")

    action = find_action()

    print(
        f"{ACTION} | status={action['status']} "
        f"| result={action.get('execution_result')} "
        f"| generation={action['execution_generation']}"
    )

    assert action["status"] == "failed"
    assert action["execution_result"] == "interrupted-by-restart"
    assert action["execution_generation"] == GENERATION

    print("FAILED STATE SURVIVED THE CRASH.")
    print("PASS")

    # ------------------------------------------------------------
    # 4. Verify audit is missing
    # ------------------------------------------------------------
    print("\n4. VERIFYING MISSING RECOVERY AUDIT:")

    recovery_before = recovery_events()
    completion_before = completion_events()

    print(
        f"Recovery audit events before recovery: "
        f"{len(recovery_before)}"
    )
    print(
        f"Completion audit events: "
        f"{len(completion_before)}"
    )

    assert len(recovery_before) == 0
    assert len(completion_before) == 0

    print("NO RECOVERY AUDIT EXISTS BEFORE RECONCILIATION.")
    print("PASS")

    # ------------------------------------------------------------
    # 5. Concurrent recovery wave
    # ------------------------------------------------------------
    print("\n5. STARTING FIRST CONCURRENT RECOVERY WAVE:")

    queue = mp.Queue()
    workers = []

    for i in range(8):
        p = mp.Process(
            target=recovery_worker,
            args=(i + 1, queue),
        )
        workers.append(p)
        p.start()

    for p in workers:
        p.join()

    results = []

    while not queue.empty():
        results.append(queue.get())

    for result in results:
        print(
            f"RECOVERY WORKER {result['worker']}: "
            f"result={result['result']} "
            f"error={result['error']}"
        )

    assert all(p.exitcode == 0 for p in workers)

    print("All concurrent recovery workers completed.")
    print("PASS")

    # ------------------------------------------------------------
    # 6. Verify state remains failed
    # ------------------------------------------------------------
    print("\n6. VERIFYING TERMINAL STATE:")

    action = find_action()

    print(
        f"{ACTION} | status={action['status']} "
        f"| result={action.get('execution_result')} "
        f"| generation={action['execution_generation']}"
    )

    assert action["status"] == "failed"
    assert action["execution_result"] == "interrupted-by-restart"
    assert action["execution_generation"] == GENERATION

    print("FAILED STATE REMAINED AUTHORITATIVE.")
    print("PASS")

    # ------------------------------------------------------------
    # 7. Exactly one recovery audit
    # ------------------------------------------------------------
    print("\n7. VERIFYING EXACTLY-ONCE RECOVERY AUDIT:")

    audits = recovery_events()

    print(f"Recovery audit events: {len(audits)}")

    for event in audits:
        print(event)

    assert len(audits) == 1

    event = audits[0]

    assert event["action"] == ACTION
    assert event["status"] == "failed"
    assert event["result"] == "interrupted-by-restart"

    print("EXACTLY ONE RECOVERY AUDIT EXISTS.")
    print("PASS")

    # ------------------------------------------------------------
    # 8. Verify no completion audit was fabricated
    # ------------------------------------------------------------
    print("\n8. VERIFYING NO FALSE COMPLETION AUDIT:")

    completions = completion_events()

    print(f"Completion audit events: {len(completions)}")

    assert len(completions) == 0

    print("NO EXECUTION COMPLETION WAS FABRICATED.")
    print("PASS")

    # ------------------------------------------------------------
    # 9. Second concurrent recovery wave
    # ------------------------------------------------------------
    print("\n9. SECOND CONCURRENT RECOVERY WAVE:")

    queue = mp.Queue()
    workers = []

    for i in range(8):
        p = mp.Process(
            target=recovery_worker,
            args=(f"SECOND-{i + 1}", queue),
        )
        workers.append(p)
        p.start()

    for p in workers:
        p.join()

    second_results = []

    while not queue.empty():
        second_results.append(queue.get())

    for result in second_results:
        print(
            f"SECOND RECOVERY {result['worker']}: "
            f"{result['result']}"
        )

    assert all(p.exitcode == 0 for p in workers)

    final_recovery = recovery_events()

    print(
        f"Final recovery audit events: "
        f"{len(final_recovery)}"
    )

    assert len(final_recovery) == 1

    print("SECOND RECOVERY WAVE WAS IDEMPOTENT.")
    print("PASS")

    # ------------------------------------------------------------
    # 10. Fresh process consistency
    # ------------------------------------------------------------
    print("\n10. FRESH-PROCESS CONSISTENCY:")

    fresh = find_action()

    fresh_recovery = recovery_events()
    fresh_completion = completion_events()

    print(
        f"{ACTION} | status={fresh['status']} "
        f"| generation={fresh['execution_generation']} "
        f"| result={fresh.get('execution_result')}"
    )

    print(
        f"Fresh recovery audits: {len(fresh_recovery)}"
    )
    print(
        f"Fresh completion audits: {len(fresh_completion)}"
    )

    assert fresh["status"] == "failed"
    assert fresh["execution_generation"] == GENERATION
    assert len(fresh_recovery) == 1
    assert len(fresh_completion) == 0

    print("FRESH PROCESS OBSERVED CONSISTENT STATE + AUDIT.")
    print("PASS")

    # ------------------------------------------------------------
    # 11. Final invariants
    # ------------------------------------------------------------
    print("\n11. FINAL HARD INVARIANTS:")
    print("REAL PROCESS CRASH OCCURRED AFTER RECOVERY STATE PERSISTENCE")
    print("FAILED STATE SURVIVED THE CRASH")
    print("RECOVERY AUDIT WAS MISSING BEFORE RECONCILIATION")
    print("CONCURRENT RECOVERY WORKERS RAN SAFELY")
    print("EXACTLY ONE RECOVERY AUDIT EXISTS")
    print("NO COMPLETION AUDIT WAS FABRICATED")
    print("EXECUTION GENERATION REMAINED STABLE")
    print("SECOND RECOVERY WAVE WAS IDEMPOTENT")
    print("NO DUPLICATE RECOVERY AUDIT WAS CREATED")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
