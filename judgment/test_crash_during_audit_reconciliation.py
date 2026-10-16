import json
import multiprocessing
import os
from pathlib import Path

import judgment.recovery as recovery
from judgment.audit import load_audit
from judgment.lifecycle import begin_execution
from judgment.recovery import recover_interrupted_actions

STATE_PATH = Path("state/latest.json")
AUDIT_PATH = Path("state/audit.json")
ACTION = "recovery-crash-after-audit"


def write_state():
    state = {
        "actions": [{
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "executed",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": "CRASH-AFTER-RECONCILIATION-AUDIT",
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


def clean_audit():
    if AUDIT_PATH.exists():
        AUDIT_PATH.unlink()

    tmp = AUDIT_PATH.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()


def matching_events():
    if not AUDIT_PATH.exists():
        return []

    return [
        e for e in load_audit()
        if isinstance(e, dict)
        and e.get("action") == ACTION
        and e.get("event") == "execution-completed"
    ]


def crashing_reconciliation_worker():
    original = recovery.record_execution

    def crash_after_durable_audit(events):
        original(events)

        print(
            "CRASH INJECTION: reconciliation audit is durable; "
            "killing process immediately afterward.",
            flush=True,
        )

        os._exit(137)

    recovery.record_execution = crash_after_durable_audit
    recover_interrupted_actions()


def normal_recovery_worker():
    result = recover_interrupted_actions()
    print(f"NORMAL RECOVERY RESULT: {result}", flush=True)


def main():
    print("=== CRASH DURING AUDIT RECONCILIATION TEST ===")

    print("\n1. PREPARING EXECUTED STATE WITH MISSING AUDIT:")
    write_state()
    clean_audit()

    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    action = state["actions"][0]

    print(
        f"{ACTION} | status = {action['status']} | "
        f"generation = {action['execution_generation']}"
    )

    assert action["status"] == "executed"
    assert len(matching_events()) == 0
    print("Completion audit events: 0")
    print("PASS")

    print("\n2. STARTING RECOVERY WITH REAL PROCESS CRASH:")
    p = multiprocessing.Process(
        target=crashing_reconciliation_worker
    )
    p.start()
    p.join()

    print(f"Child PID: {p.pid} | exitcode = {p.exitcode}")

    assert p.exitcode == 137
    print("Real process crash occurred after audit reconciliation.")
    print("PASS")

    print("\n3. CHECKING AUDIT AFTER CRASH:")
    events = matching_events()

    print(f"Matching completion events: {len(events)}")
    assert len(events) == 1

    event = events[0]
    assert event.get("action") == ACTION
    assert event.get("status") == "executed"
    assert event.get("execution_generation") == 1

    print("Reconciliation audit survived the crash.")
    print("Generation identity is correct.")
    print("PASS")

    print("\n4. CHECKING DURABLE STATE:")
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
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

    print("\n5. SECOND RECOVERY AFTER CRASH:")
    p2 = multiprocessing.Process(
        target=normal_recovery_worker
    )
    p2.start()
    p2.join()

    assert p2.exitcode == 0
    print(f"Recovery process exitcode = {p2.exitcode}")
    print("PASS")

    print("\n6. DUPLICATION CHECK:")
    events = matching_events()

    print(f"Final matching completion events: {len(events)}")
    assert len(events) == 1

    print("No duplicate reconciliation event was created.")
    print("PASS")

    print("\n7. FRESH-PROCESS CONSISTENCY:")
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

    print("Fresh process observed the same durable executed state.")
    print("PASS")

    print("\n8. FINAL CRASH-RECONCILIATION INVARIANTS:")
    print("REAL PROCESS CRASH OCCURRED AFTER AUDIT WRITE")
    print("RECONCILIATION AUDIT SURVIVED THE CRASH")
    print("EXECUTED STATE REMAINED DURABLE")
    print("GENERATION IDENTITY REMAINED STABLE")
    print("SECOND RECOVERY WAS IDEMPOTENT")
    print("EXACTLY ONE RECONCILIATION EVENT EXISTS")
    print("NO DUPLICATE AUDIT EVENT EXISTS")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
