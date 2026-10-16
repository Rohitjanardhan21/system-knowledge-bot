from __future__ import annotations

import json
import multiprocessing
import os
import time
import uuid
from pathlib import Path

from judgment.audit import load_audit, record_execution
from judgment.recovery import recover_interrupted_actions
from judgment.state_lock import state_lock


STATE_PATH = Path("state") / "latest.json"
STATE_TMP_PATH = STATE_PATH.with_suffix(".tmp")

ACTION = f"recovery-audit-first-crash-{uuid.uuid4().hex[:8]}"
GENERATION = 1
CRASH_RESULT = "AUDIT-FIRST-CRASH"


def write_state(actions):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with state_lock():
        with STATE_TMP_PATH.open("w", encoding="utf-8") as f:
            json.dump(
                {"actions": actions},
                f,
                indent=2,
            )
            f.flush()
            os.fsync(f.fileno())

        os.replace(STATE_TMP_PATH, STATE_PATH)


def read_state():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_action():
    state = read_state()

    for action in state.get("actions", []):
        if action.get("action") == ACTION:
            return action

    raise AssertionError(
        f"Action {ACTION!r} was not found in durable state."
    )


def matching_completion_events():
    return [
        event
        for event in load_audit()
        if (
            isinstance(event, dict)
            and event.get("event") == "execution-completed"
            and event.get("action") == ACTION
            and event.get("execution_generation") == GENERATION
        )
    ]


def crash_worker(audit_written, action_name, result):
    """
    Deliberately create:

        audit = executed
        lifecycle = executing

    and crash before lifecycle reconciliation.
    """

    event = {
        "event": "execution-completed",
        "action": action_name,
        "status": "executed",
        "result": result,
        "execution_generation": GENERATION,
    }

    print("CRASH INJECTION: writing durable completion audit first.")

    recorded = record_execution([event])

    print(
        "CRASH INJECTION: record_execution returned:",
        recorded,
    )

    # Verify from inside the crashing process that the audit is
    # actually visible through the project's own loader.
    local_matches = [
        x
        for x in load_audit()
        if (
            isinstance(x, dict)
            and x.get("event") == "execution-completed"
            and x.get("action") == action_name
            and x.get("execution_generation") == GENERATION
        )
    ]

    print(
        "CRASH INJECTION: matching completion events visible "
        f"inside worker: {len(local_matches)}"
    )

    assert len(local_matches) == 1

    print("CRASH INJECTION: completion audit is durable.")

    # Tell the parent that the audit has definitely been written
    # and independently verified.
    audit_written.set()

    print(
        "CRASH INJECTION: lifecycle state intentionally remains executing."
    )

    print(
        "CRASH INJECTION: killing process before lifecycle reconciliation."
    )

    os._exit(137)


def recovery_worker(worker_id, result_queue):
    try:
        result = recover_interrupted_actions()

        result_queue.put(
            {
                "worker": worker_id,
                "result": result,
                "error": None,
            }
        )

    except Exception as exc:
        result_queue.put(
            {
                "worker": worker_id,
                "result": None,
                "error": repr(exc),
            }
        )


def prepare_state():
    action = {
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "executing",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_result": None,
        "execution_generation": GENERATION,
        "execution_started_at": "2026-10-05T13:00:00+00:00",
    }

    write_state([action])


def main():
    multiprocessing.freeze_support()

    print(
        "=== RECOVERY AUDIT-FIRST CRASH + "
        "CONCURRENT RECONCILIATION TEST ==="
    )

    print("\n1. PREPARING EXECUTING STATE:")

    prepare_state()

    initial = get_action()

    print(
        f"{ACTION} | "
        f"status={initial['status']} | "
        f"generation={initial['execution_generation']}"
    )

    assert initial["status"] == "executing"
    assert initial["execution_generation"] == GENERATION

    print("PASS")

    print("\n2. STARTING REAL AUDIT-FIRST CRASH:")

    ctx = multiprocessing.get_context("spawn")

    audit_written = ctx.Event()

    crash = ctx.Process(
        target=crash_worker,
        args=(audit_written, ACTION, CRASH_RESULT),
    )

    crash.start()

    print(f"Crash worker PID: {crash.pid}")

    # Do not rely on scheduling luck. Wait until the child itself
    # confirms that record_execution() + load_audit() both succeeded.
    if not audit_written.wait(timeout=15):
        crash.join(timeout=15)
        raise AssertionError(
            "Crash worker did not confirm durable audit persistence."
        )

    crash.join(timeout=15)

    if crash.is_alive():
        crash.kill()
        crash.join()

        raise AssertionError(
            "Crash worker did not terminate after audit persistence."
        )

    print(f"Crash worker exitcode: {crash.exitcode}")

    assert crash.exitcode == 137

    print(
        "REAL PROCESS CRASH OCCURRED AFTER AUDIT PERSISTENCE."
    )
    print("PASS")

    print("\n3. VERIFYING PRE-RECOVERY MISMATCH:")

    before = get_action()
    completions = matching_completion_events()

    print(
        f"{ACTION} | "
        f"status={before['status']} | "
        f"result={before.get('execution_result')} | "
        f"generation={before['execution_generation']}"
    )

    print(
        f"Current-generation completion audits: {len(completions)}"
    )

    assert before["status"] == "executing"
    assert before["execution_result"] is None
    assert before["execution_generation"] == GENERATION

    assert len(completions) == 1

    completion = completions[0]

    assert completion["event"] == "execution-completed"
    assert completion["action"] == ACTION
    assert completion["status"] == "executed"
    assert completion["result"] == CRASH_RESULT
    assert completion["execution_generation"] == GENERATION

    print(
        "Audit exists while lifecycle state is still executing."
    )
    print("Audit-first mismatch established correctly.")
    print("PASS")

    print("\n4. STARTING CONCURRENT RECOVERY WAVE:")

    result_queue = ctx.Queue()
    workers = []

    for worker_id in range(1, 9):
        p = ctx.Process(
            target=recovery_worker,
            args=(worker_id, result_queue),
        )

        workers.append(p)
        p.start()

    results = []

    for _ in workers:
        results.append(result_queue.get(timeout=30))

    for p in workers:
        p.join(timeout=30)

    for p in workers:
        assert not p.is_alive()

    for result in sorted(
        results,
        key=lambda x: x["worker"],
    ):
        print(
            f"RECOVERY WORKER {result['worker']}: "
            f"result={result['result']} "
            f"error={result['error']}"
        )

        assert result["error"] is None

    print("All concurrent recovery workers completed.")
    print("PASS")

    print("\n5. VERIFYING POST-RECOVERY STATE:")

    after = get_action()

    print(
        f"{ACTION} | "
        f"status={after['status']} | "
        f"result={after.get('execution_result')} | "
        f"generation={after['execution_generation']}"
    )

    assert after["execution_generation"] == GENERATION

    if after["status"] != "executed":
        raise AssertionError(
            "\nAUDIT-FIRST RECOVERY GAP DETECTED\n"
            f"Action: {ACTION}\n"
            f"Generation: {GENERATION}\n"
            f"Lifecycle status: {after['status']}\n"
            f"Lifecycle result: {after.get('execution_result')}\n"
            "\n"
            "The completion audit exists and identifies this generation "
            "as executed, but recovery did not reconcile the lifecycle "
            "state from executing -> executed."
        )

    assert after["execution_result"] == CRASH_RESULT

    print(
        "AUDIT-FIRST LIFECYCLE RECONCILIATION SUCCEEDED."
    )
    print("PASS")

    print("\n6. VERIFYING EXACTLY-ONCE COMPLETION AUDIT:")

    final_completions = matching_completion_events()

    print(
        f"Generation completion audits: "
        f"{len(final_completions)}"
    )

    assert len(final_completions) == 1

    print("Exactly ONE completion audit exists.")
    print("PASS")

    print("\n7. SECOND CONCURRENT RECOVERY WAVE:")

    second_queue = ctx.Queue()
    second_workers = []

    for worker_id in range(1, 9):
        p = ctx.Process(
            target=recovery_worker,
            args=(f"SECOND-{worker_id}", second_queue),
        )

        second_workers.append(p)
        p.start()

    second_results = []

    for _ in second_workers:
        second_results.append(
            second_queue.get(timeout=30)
        )

    for p in second_workers:
        p.join(timeout=30)

    for p in second_workers:
        assert not p.is_alive()

    for result in sorted(
        second_results,
        key=lambda x: str(x["worker"]),
    ):
        print(
            f"SECOND RECOVERY {result['worker']}: "
            f"{result['result']}"
        )

        assert result["error"] is None

    second_completions = matching_completion_events()

    print(
        f"Final completion audits: "
        f"{len(second_completions)}"
    )

    assert len(second_completions) == 1

    print("Second recovery wave created no duplicate.")
    print("PASS")

    print("\n8. FRESH-PROCESS CONSISTENCY:")

    fresh = get_action()
    fresh_completions = matching_completion_events()

    print(
        f"{ACTION} | "
        f"status={fresh['status']} | "
        f"generation={fresh['execution_generation']} | "
        f"result={fresh.get('execution_result')}"
    )

    print(
        f"Fresh-process completion audits: "
        f"{len(fresh_completions)}"
    )

    assert fresh["status"] == "executed"
    assert fresh["execution_generation"] == GENERATION
    assert fresh["execution_result"] == CRASH_RESULT
    assert len(fresh_completions) == 1

    print(
        "Fresh process observed consistent state + audit."
    )
    print("PASS")

    print("\n9. FINAL HARD INVARIANTS:")

    print("REAL PROCESS CRASH OCCURRED AFTER AUDIT PERSISTENCE")
    print("AUDIT REMAINED GENERATION-SPECIFIC")
    print("LIFECYCLE STATE STARTED AS EXECUTING")
    print("AUDIT-FIRST RECONCILIATION PRODUCED EXECUTED STATE")
    print("EXECUTION GENERATION REMAINED STABLE")
    print("EXACTLY ONE COMPLETION AUDIT EXISTS")
    print("NO DUPLICATE COMPLETION WAS CREATED")
    print("SECOND RECOVERY WAVE WAS IDEMPOTENT")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
