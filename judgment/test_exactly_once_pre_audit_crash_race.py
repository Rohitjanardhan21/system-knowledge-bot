from __future__ import annotations

import json
import multiprocessing
import os
import time
import uuid
from pathlib import Path

from judgment.audit import load_audit
from judgment.recovery import recover_interrupted_actions


STATE_PATH = Path("state") / "latest.json"


def read_action_state(action_name):
    with STATE_PATH.open("r", encoding="utf-8") as f:
        state = json.load(f)

    for action in state.get("actions", []):
        if action.get("action") == action_name:
            return action

    return None


def write_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    tmp = STATE_PATH.with_suffix(".tmp")

    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, STATE_PATH)


def crash_worker(action_name):
    """
    Simulate the exact dangerous boundary:
    durable EXECUTED state exists, but completion audit has not
    yet been written.
    """
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    for action in state["actions"]:
        if action["action"] == action_name:
            action["status"] = "executed"
            action["execution_result"] = "PRE-AUDIT-CRASH"
            action["execution_completed_at"] = (
                "2026-10-05T07:00:00+00:00"
            )
            break

    write_state(state)

    print(
        "CRASH INJECTION: durable executed state persisted; "
        "completion audit intentionally missing."
    )

    # Real process crash.
    os._exit(137)


def recovery_worker():
    try:
        result = recover_interrupted_actions()
        print(f"RECOVERY: {result}")
    except Exception as exc:
        print(f"RECOVERY ERROR: {exc}")
        raise


def completion_events(action_name, generation):
    return [
        event
        for event in load_audit()
        if (
            isinstance(event, dict)
            and event.get("event") == "execution-completed"
            and event.get("action") == action_name
            and event.get("execution_generation") == generation
        )
    ]


def main():
    multiprocessing.freeze_support()

    action_name = f"exactly-once-pre-audit-crash-{uuid.uuid4().hex[:8]}"
    generation = 1

    print("=== EXACTLY-ONCE PRE-AUDIT CRASH + RECOVERY RACE TEST ===")

    # ------------------------------------------------------------
    # 1. PREPARE CLEAN EXECUTED STATE WITH NO COMPLETION AUDIT
    # ------------------------------------------------------------
    print("\n1. PREPARING EXECUTED STATE WITH MISSING AUDIT:")

    state = {
        "actions": [
            {
                "action": action_name,
                "priority": "high",
                "execution_mode": "automatic",
                "status": "executing",
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
                "execution_result": None,
                "execution_generation": generation,
                "execution_started_at": "2026-10-05T07:00:00+00:00",
            }
        ]
    }

    write_state(state)

    # Ensure this test starts with no matching completion audit.
    before = completion_events(action_name, generation)

    print(
        f"{action_name} | status=executing | "
        f"generation={generation}"
    )
    print(f"Completion audit events before crash: {len(before)}")
    assert len(before) == 0

    print("PASS")

    # ------------------------------------------------------------
    # 2. REAL PROCESS CRASH AFTER STATE PERSISTENCE
    # ------------------------------------------------------------
    print("\n2. STARTING REAL PRE-AUDIT CRASH WORKER:")

    crash = multiprocessing.Process(
        target=crash_worker,
        args=(action_name,),
    )

    crash.start()

    crash.join(timeout=10)

    print(f"Crash worker PID: {crash.pid}")
    print(f"Crash worker exitcode: {crash.exitcode}")

    assert crash.exitcode == 137

    print("REAL PROCESS CRASH OCCURRED.")
    print("PASS")

    # ------------------------------------------------------------
    # 3. VERIFY STATE SURVIVED WITHOUT AUDIT
    # ------------------------------------------------------------
    print("\n3. CHECKING DURABLE STATE BEFORE RECOVERY:")

    current = read_action_state(action_name)

    print(
        f"{action_name} | "
        f"status={current['status']} | "
        f"result={current['execution_result']} | "
        f"generation={current['execution_generation']}"
    )

    assert current["status"] == "executed"
    assert current["execution_result"] == "PRE-AUDIT-CRASH"
    assert current["execution_generation"] == generation

    print("Durable executed state survived the crash.")
    print("PASS")

    # ------------------------------------------------------------
    # 4. VERIFY AUDIT IS STILL MISSING
    # ------------------------------------------------------------
    print("\n4. VERIFYING MISSING COMPLETION AUDIT:")

    missing = completion_events(action_name, generation)

    print(f"Matching completion events: {len(missing)}")

    assert len(missing) == 0

    print("No fabricated completion event exists before recovery.")
    print("PASS")

    # ------------------------------------------------------------
    # 5. CONCURRENT RECOVERY WAVE
    # ------------------------------------------------------------
    print("\n5. STARTING CONCURRENT RECOVERY WAVE:")

    workers = []

    for i in range(8):
        p = multiprocessing.Process(
            target=recovery_worker
        )
        p.start()
        workers.append((i + 1, p))

    for worker_id, p in workers:
        p.join(timeout=10)
        print(
            f"RECOVERY WORKER {worker_id}: "
            f"exitcode={p.exitcode}"
        )
        assert p.exitcode == 0

    print("All concurrent recovery workers completed.")
    print("PASS")

    # ------------------------------------------------------------
    # 6. EXACTLY-ONCE RECONCILIATION
    # ------------------------------------------------------------
    print("\n6. CHECKING RECONCILIATION:")

    events = completion_events(action_name, generation)

    print(f"Completion audit events: {len(events)}")

    assert len(events) == 1

    event = events[0]

    assert event["status"] == "executed"
    assert event["action"] == action_name
    assert event["execution_generation"] == generation
    assert event["result"] == "PRE-AUDIT-CRASH"

    print("Exactly ONE completion audit exists.")
    print("Generation identity is correct.")
    print("PASS")

    # ------------------------------------------------------------
    # 7. DURABLE STATE MUST REMAIN EXECUTED
    # ------------------------------------------------------------
    print("\n7. VERIFYING FINAL DURABLE STATE:")

    final_state = read_action_state(action_name)

    print(
        f"{action_name} | "
        f"status={final_state['status']} | "
        f"result={final_state['execution_result']} | "
        f"generation={final_state['execution_generation']}"
    )

    assert final_state["status"] == "executed"
    assert final_state["execution_result"] == "PRE-AUDIT-CRASH"
    assert final_state["execution_generation"] == generation

    print("Executed state remained authoritative.")
    print("PASS")

    # ------------------------------------------------------------
    # 8. SECOND RECOVERY MUST BE IDEMPOTENT
    # ------------------------------------------------------------
    print("\n8. SECOND RECOVERY / DUPLICATION CHECK:")

    second = recover_interrupted_actions()

    print(f"SECOND RECOVERY RESULT: {second}")

    assert action_name not in second

    final_events = completion_events(
        action_name,
        generation,
    )

    print(
        f"Final completion audit events: "
        f"{len(final_events)}"
    )

    assert len(final_events) == 1

    print("Second recovery created no duplicate.")
    print("PASS")

    # ------------------------------------------------------------
    # 9. FRESH-PROCESS CONSISTENCY
    # ------------------------------------------------------------
    print("\n9. FRESH-PROCESS CONSISTENCY:")

    verifier = multiprocessing.Process(
        target=recovery_worker
    )

    verifier.start()
    verifier.join(timeout=10)

    assert verifier.exitcode == 0

    fresh_state = read_action_state(action_name)
    fresh_events = completion_events(
        action_name,
        generation,
    )

    print(
        f"{action_name} | "
        f"status={fresh_state['status']} | "
        f"generation={fresh_state['execution_generation']} | "
        f"result={fresh_state['execution_result']}"
    )

    print(
        f"Fresh-process completion events: "
        f"{len(fresh_events)}"
    )

    assert fresh_state["status"] == "executed"
    assert fresh_state["execution_generation"] == generation
    assert len(fresh_events) == 1

    print("Fresh process observed consistent state + audit.")
    print("PASS")

    # ------------------------------------------------------------
    # 10. HARD INVARIANTS
    # ------------------------------------------------------------
    print("\n10. FINAL HARD INVARIANTS:")
    print("REAL PROCESS CRASH OCCURRED BEFORE AUDIT")
    print("DURABLE EXECUTED STATE SURVIVED")
    print("NO COMPLETION AUDIT EXISTED BEFORE RECOVERY")
    print("CONCURRENT RECOVERY RECONCILED THE MISSING AUDIT")
    print("EXACTLY ONE COMPLETION AUDIT EXISTS")
    print("EXECUTION GENERATION REMAINED STABLE")
    print("SECOND RECOVERY WAS IDEMPOTENT")
    print("NO DUPLICATE COMPLETION WAS CREATED")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT")
    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
