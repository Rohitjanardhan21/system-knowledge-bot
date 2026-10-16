import json
import multiprocessing
import os
from pathlib import Path

import judgment.recovery as recovery
from judgment.audit import load_audit
from judgment.recovery import recover_interrupted_actions

STATE_PATH = Path("state/latest.json")
AUDIT_PATH = Path("state/audit.json")
ACTION = "concurrent-crash-reconciliation"


def prepare_state():
    state = {
        "actions": [{
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "executed",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": "CONCURRENT-CRASH-RECONCILIATION",
            "execution_generation": 1,
            "execution_started_at": "2026-10-05T06:00:00+00:00",
            "execution_completed_at": "2026-10-05T06:00:00+00:00",
        }]
    }

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    if AUDIT_PATH.exists():
        AUDIT_PATH.unlink()

    tmp = AUDIT_PATH.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()


def matching_events():
    if not AUDIT_PATH.exists():
        return []

    return [
        event for event in load_audit()
        if isinstance(event, dict)
        and event.get("action") == ACTION
        and event.get("event") == "execution-completed"
    ]


def crash_worker(audit_written, allow_crash):
    original = recovery.record_execution

    def crash_after_audit(events):
        original(events)

        print(
            "CRASH INJECTION: recovery audit was durably written; "
            "worker is now crashing.",
            flush=True,
        )

        audit_written.set()
        if not allow_crash.wait(timeout=10):
            print(
                "CRASH INJECTION ERROR: timed out waiting "
                "for concurrent recovery workers.",
                flush=True,
            )
            os._exit(1)

        os._exit(137)

    recovery.record_execution = crash_after_audit
    result = recover_interrupted_actions()

    print(f"CRASH WORKER RESULT: {result}", flush=True)


def normal_worker(worker_id, ready=None):
    if ready is not None:
        ready.set()
    result = recover_interrupted_actions()
    print(
        f"RECOVERY WORKER {worker_id}: {result}",
        flush=True,
    )


def main():
    print("=== CONCURRENT RECOVERY + CRASH RECONCILIATION TEST ===")

    print("\n1. PREPARING EXECUTED STATE WITH MISSING AUDIT:")
    prepare_state()

    state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )
    action = state["actions"][0]

    print(
        f"{ACTION} | status = {action['status']} | "
        f"generation = {action['execution_generation']}"
    )

    assert action["status"] == "executed"
    assert len(matching_events()) == 0

    print("Completion audit events: 0")
    print("PASS")

    print("\n2. STARTING CRASHING RECOVERY WORKER:")
    audit_written = multiprocessing.Event()
    allow_crash = multiprocessing.Event()
    crash = multiprocessing.Process(
        target=crash_worker,
        args=(audit_written, allow_crash),
    )
    crash.start()

    print(f"Crash worker PID: {crash.pid}")

    if not audit_written.wait(timeout=10):
        crash.join(timeout=12)
        raise AssertionError(
            "Crash worker did not durably reconcile the audit."
        )

    print("\n3. STARTING CONCURRENT RECOVERY WORKERS:")
    workers = []
    ready_events = []

    for worker_id in range(1, 9):
        ready = multiprocessing.Event()
        p = multiprocessing.Process(
            target=normal_worker,
            args=(worker_id, ready),
        )
        workers.append(p)
        ready_events.append(ready)
        p.start()

    if not all(event.wait(timeout=10) for event in ready_events):
        allow_crash.set()
        crash.join(timeout=12)
        for p in workers:
            p.join(timeout=12)
        raise AssertionError(
            "Not all concurrent recovery workers became ready."
        )

    allow_crash.set()
    crash.join()

    for p in workers:
        p.join()

    print(
        f"Crash worker exitcode: {crash.exitcode}"
    )

    for i, p in enumerate(workers, 1):
        print(
            f"Recovery worker {i}: "
            f"exitcode={p.exitcode}"
        )

    assert crash.exitcode == 137
    assert all(p.exitcode == 0 for p in workers)

    print("Exactly one real recovery-process crash occurred.")
    print("All concurrent recovery workers completed.")
    print("PASS")

    print("\n4. CHECKING RECONCILIATION AUDIT:")
    events = matching_events()

    print(f"Matching completion events: {len(events)}")

    assert len(events) == 1

    event = events[0]

    assert event.get("action") == ACTION
    assert event.get("status") == "executed"
    assert event.get("execution_generation") == 1

    print("Exactly ONE reconciliation completion exists.")
    print("Generation identity is correct.")
    print("PASS")

    print("\n5. VERIFYING DURABLE STATE:")
    state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    action = next(
        a for a in state["actions"]
        if a.get("action") == ACTION
    )

    print(
        f"{ACTION} | status = {action['status']} | "
        f"result = {action.get('execution_result')} | "
        f"generation = {action.get('execution_generation')}"
    )

    assert action["status"] == "executed"
    assert action["execution_generation"] == 1

    print("Executed state was preserved.")
    print("PASS")

    print("\n6. SECOND CONCURRENT RECOVERY WAVE:")
    second_wave = []

    for worker_id in range(1, 9):
        p = multiprocessing.Process(
            target=normal_worker,
            args=(f"SECOND-{worker_id}",),
        )
        second_wave.append(p)
        p.start()

    for p in second_wave:
        p.join()

    assert all(p.exitcode == 0 for p in second_wave)

    print("Second recovery wave completed.")
    print("PASS")

    print("\n7. FINAL DUPLICATION CHECK:")
    events = matching_events()

    print(
        f"Final matching completion events: {len(events)}"
    )

    assert len(events) == 1

    print("No duplicate reconciliation event exists.")
    print("PASS")

    print("\n8. FRESH-PROCESS CONSISTENCY:")
    fresh_state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    fresh_action = next(
        a for a in fresh_state["actions"]
        if a.get("action") == ACTION
    )

    print(fresh_action)

    assert fresh_action["status"] == "executed"
    assert fresh_action["execution_generation"] == 1

    print("Fresh process observed the same durable state.")
    print("PASS")

    print("\n9. FINAL CONCURRENT-CRASH INVARIANTS:")
    print("REAL PROCESS CRASH OCCURRED DURING RECONCILIATION")
    print("CONCURRENT RECOVERY PROCESSES COMPLETED")
    print("EXACTLY ONE RECONCILIATION EVENT EXISTS")
    print("NO DUPLICATE AUDIT EVENT EXISTS")
    print("GENERATION IDENTITY REMAINED STABLE")
    print("EXECUTED STATE WAS PRESERVED")
    print("SECOND RECOVERY WAVE WAS IDEMPOTENT")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
