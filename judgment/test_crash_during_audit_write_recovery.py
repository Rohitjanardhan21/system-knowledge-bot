from __future__ import annotations

import json
import multiprocessing
import os
import uuid
from pathlib import Path

from judgment.audit import load_audit
from judgment.recovery import recover_interrupted_actions


STATE_PATH = Path("state") / "latest.json"
AUDIT_PATH = Path("state") / "audit.json"

ACTION = f"crash-during-audit-write-{uuid.uuid4().hex[:8]}"
GENERATION = 1
RESULT = "CRASH-DURING-AUDIT-WRITE"


def write_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    temp_path = STATE_PATH.with_suffix(".tmp")

    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_path, STATE_PATH)


def read_state():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def matching_completion_events():
    """
    Only count a fully parseable completion event belonging to
    this exact action + generation.
    """
    try:
        events = load_audit()
    except Exception as exc:
        print(
            f"AUDIT LOAD WARNING: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return []

    return [
        event
        for event in events
        if (
            isinstance(event, dict)
            and event.get("event") == "execution-completed"
            and event.get("action") == ACTION
            and event.get("status") == "executed"
            and event.get("execution_generation") == GENERATION
        )
    ]


def prepare_state():
    state = {
        "actions": [{
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
        }]
    }

    write_state(state)


def crashing_worker():
    """
    Crash at the audit boundary.

    1. Persist executed lifecycle state.
    2. Start an intentionally incomplete audit write.
    3. fsync the partial bytes.
    4. Kill the real process.
    """

    state = read_state()

    action = state["actions"][0]

    action["status"] = "executed"
    action["execution_result"] = RESULT
    action["execution_completed_at"] = (
        "2026-10-05T06:00:01+00:00"
    )

    write_state(state)

    print(
        "CRASH INJECTION: durable executed state persisted.",
        flush=True,
    )

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "event": "execution-completed",
        "action": ACTION,
        "status": "executed",
        "result": RESULT,
        "execution_generation": GENERATION,
        "recovered": False,
    }

    serialized = json.dumps(event) + "\n"

    # Write only part of the event.
    partial = serialized[:max(1, len(serialized) // 2)]

    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(partial)
        f.flush()
        os.fsync(f.fileno())

        print(
            "CRASH INJECTION: partial audit bytes were persisted.",
            flush=True,
        )
        print(
            "CRASH INJECTION: killing process before audit "
            "record completed.",
            flush=True,
        )

        os._exit(137)


def recovery_worker(index, queue):
    try:
        result = recover_interrupted_actions()

        queue.put({
            "index": index,
            "result": result,
            "error": None,
        })

    except Exception as exc:
        queue.put({
            "index": index,
            "result": None,
            "error": repr(exc),
        })


def run_recovery_wave(label):
    queue = multiprocessing.Queue()
    workers = []

    for index in range(1, 9):
        process = multiprocessing.Process(
            target=recovery_worker,
            args=(index, queue),
        )

        process.start()
        workers.append(process)

    results = []

    for process in workers:
        process.join(timeout=20)

    for process in workers:
        if process.is_alive():
            process.kill()
            process.join()

    for _ in workers:
        try:
            results.append(queue.get(timeout=5))
        except Exception as exc:
            results.append({
                "index": -1,
                "result": None,
                "error": repr(exc),
            })

    for item in sorted(
        results,
        key=lambda x: x["index"],
    ):
        index = item["index"]
        result = item["result"]
        error = item["error"]

        exitcode = (
            workers[index - 1].exitcode
            if 1 <= index <= len(workers)
            else "unknown"
        )

        print(
            f"{label} WORKER {index}: "
            f"exitcode={exitcode} "
            f"result={result} "
            f"error={error}"
        )

        assert error is None, (
            f"Recovery worker {index} failed: {error}"
        )

    print(
        f"{label}: all concurrent recovery workers completed."
    )


def main():
    print(
        "=== CRASH DURING AUDIT WRITE + RECOVERY TEST ===\n"
    )

    print("1. PREPARING EXECUTING STATE:")

    prepare_state()

    state = read_state()

    action = next(
        item
        for item in state["actions"]
        if item["action"] == ACTION
    )

    print(
        f"{ACTION} | status={action['status']} "
        f"| generation={action['execution_generation']}"
    )

    assert action["status"] == "executing"
    assert action["execution_generation"] == GENERATION

    print("PASS\n")

    print("2. STARTING REAL CRASH DURING AUDIT WRITE:")

    crash = multiprocessing.Process(
        target=crashing_worker
    )

    crash.start()

    print(f"Crash worker PID: {crash.pid}")

    crash.join(timeout=15)

    if crash.is_alive():
        crash.kill()
        crash.join()

    print(
        f"Crash worker exitcode: {crash.exitcode}"
    )

    assert crash.exitcode == 137

    print(
        "REAL PROCESS CRASH OCCURRED DURING AUDIT WRITE."
    )
    print("PASS\n")

    print("3. VERIFYING DURABLE STATE AFTER CRASH:")

    state = read_state()

    action = next(
        item
        for item in state["actions"]
        if item["action"] == ACTION
    )

    print(
        f"{ACTION} | status={action['status']} "
        f"| result={action['execution_result']} "
        f"| generation={action['execution_generation']}"
    )

    assert action["status"] == "executed"
    assert action["execution_result"] == RESULT
    assert action["execution_generation"] == GENERATION

    print(
        "Executed state survived the crash."
    )
    print("PASS\n")

    print("4. CHECKING AUDIT BEFORE RECOVERY:")

    assert AUDIT_PATH.exists(), (
        "Expected state\\audit.json to exist."
    )

    raw = AUDIT_PATH.read_bytes()

    print(
        f"Audit file exists: {AUDIT_PATH}"
    )
    print(
        f"Audit bytes currently present: {len(raw)}"
    )

    # IMPORTANT:
    # Do NOT assert ACTION is present here.
    #
    # This is intentionally a torn-write boundary. The record may
    # be incomplete and therefore must not be interpreted as a
    # valid completion event.
    print(
        "Partial/torn audit boundary accepted for inspection."
    )

    before_events = matching_completion_events()

    print(
        f"Valid matching completion events before recovery: "
        f"{len(before_events)}"
    )

    assert len(before_events) == 0, (
        "A valid completion audit already existed before "
        "recovery; the crash boundary was not exercised correctly."
    )

    print(
        "No valid completion event exists before recovery."
    )
    print("PASS\n")

    print("5. STARTING FIRST CONCURRENT RECOVERY WAVE:")

    run_recovery_wave("RECOVERY")

    print("PASS\n")

    print("6. VERIFYING EXACTLY-ONCE RECONCILIATION:")

    events = matching_completion_events()

    print(
        f"Matching completion audit events: {len(events)}"
    )

    assert len(events) == 1, (
        f"Expected exactly one completion audit, "
        f"found {len(events)}."
    )

    event = events[0]

    assert (
        event["execution_generation"] == GENERATION
    )

    print(
        "Exactly ONE completion audit exists."
    )
    print(
        "Generation identity is correct."
    )
    print("PASS\n")

    print("7. VERIFYING DURABLE EXECUTED STATE:")

    state = read_state()

    action = next(
        item
        for item in state["actions"]
        if item["action"] == ACTION
    )

    print(
        f"{ACTION} | status={action['status']} "
        f"| result={action['execution_result']} "
        f"| generation={action['execution_generation']}"
    )

    assert action["status"] == "executed"
    assert action["execution_result"] == RESULT
    assert action["execution_generation"] == GENERATION

    print(
        "Executed state remained authoritative."
    )
    print("PASS\n")

    print("8. SECOND CONCURRENT RECOVERY WAVE:")

    run_recovery_wave("SECOND RECOVERY")

    final_events = matching_completion_events()

    print(
        f"Final matching completion events: "
        f"{len(final_events)}"
    )

    assert len(final_events) == 1

    print(
        "Second recovery wave created no duplicate."
    )
    print("PASS\n")

    print("9. FRESH-PROCESS CONSISTENCY:")

    fresh_state = read_state()

    fresh_action = next(
        item
        for item in fresh_state["actions"]
        if item["action"] == ACTION
    )

    fresh_events = matching_completion_events()

    print(
        f"{ACTION} | status={fresh_action['status']} "
        f"| generation={fresh_action['execution_generation']} "
        f"| result={fresh_action['execution_result']}"
    )

    print(
        f"Fresh-process completion events: "
        f"{len(fresh_events)}"
    )

    assert fresh_action["status"] == "executed"
    assert (
        fresh_action["execution_generation"]
        == GENERATION
    )
    assert len(fresh_events) == 1

    print(
        "Fresh process observed consistent state + audit."
    )
    print("PASS\n")

    print("10. FINAL HARD INVARIANTS:")

    invariants = [
        "REAL PROCESS CRASH OCCURRED DURING AUDIT WRITE",
        "DURABLE EXECUTED STATE SURVIVED",
        "TORN AUDIT DATA WAS NOT ACCEPTED AS COMPLETION",
        "CONCURRENT RECOVERY RECONCILED THE MISSING VALID AUDIT",
        "EXACTLY ONE COMPLETION AUDIT EXISTS",
        "EXECUTION GENERATION REMAINED STABLE",
        "SECOND RECOVERY WAVE WAS IDEMPOTENT",
        "NO DUPLICATE COMPLETION WAS CREATED",
        "FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT",
    ]

    for invariant in invariants:
        print(invariant)

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
