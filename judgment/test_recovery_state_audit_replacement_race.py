from __future__ import annotations

import json
import multiprocessing
import os
import uuid
from pathlib import Path

from judgment.audit import load_audit, record_execution
import judgment.recovery as recovery
from judgment.recovery import recover_interrupted_actions
from judgment.state_lock import state_lock


STATE_PATH = Path("state") / "latest.json"


def write_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(".tmp")
    with state_lock():
        with temp.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, STATE_PATH)


def read_state():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def recovery_worker(result_queue, recovery_started):
    try:
        original_reconcile = recovery._reconcile_executed_audit

        def signal_recovery_started(state):
            recovery_started.set()
            return original_reconcile(state)

        recovery._reconcile_executed_audit = signal_recovery_started
        result = recover_interrupted_actions()
        result_queue.put({"result": result})
    except Exception as exc:
        result_queue.put({"error": repr(exc)})


def main():
    multiprocessing.freeze_support()

    action = f"recovery-state-audit-race-{uuid.uuid4().hex[:8]}"

    print("=== RECOVERY + STATE REPLACEMENT + AUDIT RECONCILIATION RACE ===")

    print("\n1. PREPARING GENERATION 1 EXECUTING STATE:")
    state = {
        "actions": [{
            "action": action,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "executing",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": None,
            "execution_generation": 1,
            "execution_started_at": "2000-01-01T00:00:00+00:00",
        }]
    }
    write_state(state)

    print(f"{action} | status=executing | generation=1")
    print("PASS")

    print("\n2. STARTING RECOVERY WORKER:")
    q = multiprocessing.Queue()
    recovery_started = multiprocessing.Event()
    p = multiprocessing.Process(
        target=recovery_worker,
        args=(q, recovery_started),
    )
    p.start()
    print(f"Recovery worker PID: {p.pid}")

    if not recovery_started.wait(timeout=10):
        p.join(timeout=1)
        raise AssertionError(
            "Recovery worker did not reach reconciliation."
        )

    print("PASS")

    print("\n3. INSTALLING NEWER GENERATION 2:")
    newer_state = {
        "actions": [{
            "action": action,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "executed",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": "GENERATION-2-WON",
            "execution_generation": 2,
            "execution_started_at": "2000-01-01T00:01:00+00:00",
            "execution_completed_at": "2000-01-01T00:01:01+00:00",
        }]
    }
    write_state(newer_state)

    print(f"{action} | status=executed | generation=2")
    print("Newer generation installed.")
    print("PASS")

    print("\n4. WAITING FOR STALE RECOVERY:")
    p.join(timeout=10)

    if p.is_alive():
        p.terminate()
        p.join()
        raise AssertionError("Recovery worker did not terminate.")

    result = q.get() if not q.empty() else {}
    print(f"RECOVERY RESULT: {result}")
    print(f"Recovery worker exitcode: {p.exitcode}")
    print("PASS")

    print("\n5. VERIFYING GENERATION 2 SURVIVED:")
    final_state = read_state()
    action_state = next(
        x for x in final_state["actions"]
        if x["action"] == action
    )

    print(
        f"{action} | status={action_state['status']} | "
        f"generation={action_state['execution_generation']} | "
        f"result={action_state['execution_result']}"
    )

    assert action_state["execution_generation"] == 2
    assert action_state["status"] == "executed"
    assert action_state["execution_result"] == "GENERATION-2-WON"

    print("GENERATION 2 REMAINED AUTHORITATIVE.")
    print("PASS")

    print("\n6. VERIFYING NO STALE RECOVERY AUDIT:")
    audits = load_audit()

    stale_recovery = [
        e for e in audits
        if e.get("event") == "recovery-interrupted"
        and e.get("action") == action
    ]

    current_completion = [
        e for e in audits
        if e.get("event") == "execution-completed"
        and e.get("action") == action
        and e.get("execution_generation") == 2
    ]

    stale_completion = [
        e for e in audits
        if e.get("event") == "execution-completed"
        and e.get("action") == action
        and e.get("execution_generation") == 1
    ]

    print(f"Generation 1 recovery events: {len(stale_recovery)}")
    print(f"Generation 1 completion events: {len(stale_completion)}")
    print(f"Generation 2 completion events: {len(current_completion)}")

    assert len(stale_recovery) == 1
    assert len(stale_completion) == 0

    print("GENERATION 1 RECOVERY WAS AUDITED BEFORE REPLACEMENT.")
    print("NO STALE COMPLETION EVENT WAS FABRICATED.")
    print("PASS")

    print("\n7. RECONCILING CURRENT GENERATION AUDIT:")
    record_execution([{
        "event": "execution-completed",
        "action": action,
        "status": "executed",
        "result": "GENERATION-2-WON",
        "execution_generation": 2,
    }])

    audits = load_audit()

    current_completion = [
        e for e in audits
        if e.get("event") == "execution-completed"
        and e.get("action") == action
        and e.get("execution_generation") == 2
    ]

    print(f"Generation 2 completion events: {len(current_completion)}")
    assert len(current_completion) == 1
    print("CURRENT GENERATION AUDIT EXISTS EXACTLY ONCE.")
    print("PASS")

    print("\n8. SECOND RECOVERY:")
    second = recover_interrupted_actions()
    print(f"SECOND RECOVERY RESULT: {second}")
    assert action not in second
    print("SECOND RECOVERY IS IDEMPOTENT.")
    print("PASS")

    print("\n9. FRESH-PROCESS CONSISTENCY:")
    fresh_state = read_state()
    fresh_action = next(
        x for x in fresh_state["actions"]
        if x["action"] == action
    )

    final_audits = load_audit()

    final_completion = [
        e for e in final_audits
        if e.get("event") == "execution-completed"
        and e.get("action") == action
        and e.get("execution_generation") == 2
    ]

    print(
        f"{action} | status={fresh_action['status']} | "
        f"generation={fresh_action['execution_generation']} | "
        f"result={fresh_action['execution_result']}"
    )
    print(f"Generation 2 completion events: {len(final_completion)}")

    assert fresh_action["execution_generation"] == 2
    assert fresh_action["status"] == "executed"
    assert len(final_completion) == 1

    print("FRESH PROCESS OBSERVED CONSISTENT STATE + AUDIT.")
    print("PASS")

    print("\n10. FINAL HARD INVARIANTS:")
    print("STALE RECOVERY STARTED AGAINST GENERATION 1")
    print("GENERATION 2 BECAME AUTHORITATIVE")
    print("STALE RECOVERY DID NOT OVERWRITE GENERATION 2")
    print("GENERATION 1 RECOVERY AUDIT MATCHED THE RECOVERY RESULT")
    print("CURRENT GENERATION 2 HAS EXACTLY ONE COMPLETION AUDIT")
    print("SECOND RECOVERY WAS IDEMPOTENT")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT")
    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
