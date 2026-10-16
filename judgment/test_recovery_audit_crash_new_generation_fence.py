from __future__ import annotations

import json
import multiprocessing as mp
import os
import uuid
from pathlib import Path

from judgment.audit import load_audit
import judgment.recovery as recovery


STATE_PATH = Path("state") / "latest.json"
ACTION = f"recovery-audit-crash-new-generation-{uuid.uuid4().hex[:8]}"
GEN1 = 1
GEN2 = 2


def write_state(action, generation, status, result=None):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "actions": [{
            "action": action,
            "priority": "high",
            "execution_mode": "automatic",
            "status": status,
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": result,
            "execution_generation": generation,
            "execution_started_at": "2026-10-05T08:00:00+00:00",
        }]
    }

    temp = STATE_PATH.with_suffix(".tmp")

    with temp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp, STATE_PATH)


def read_action():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        state = json.load(f)

    for action in state.get("actions", []):
        if action.get("action") == ACTION:
            return action

    raise AssertionError(f"Action {ACTION} not found")


def completion_events(generation):
    return [
        event for event in load_audit()
        if isinstance(event, dict)
        and event.get("event") == "execution-completed"
        and event.get("action") == ACTION
        and event.get("execution_generation") == generation
        and event.get("status") == "executed"
    ]


def crashing_recovery_worker(ready, proceed, action_name, generation):
    original_record_execution = recovery.record_execution

    def crash_after_reconciliation_audit(events):
        original_record_execution(events)

        matching = [
            event for event in events
            if isinstance(event, dict)
            and event.get("event") == "execution-completed"
            and event.get("action") == action_name
            and event.get("execution_generation") == generation
        ]

        if matching:
            print(
                "CRASH INJECTION: Generation-1 reconciliation audit "
                "is durable; crashing process now.",
                flush=True,
            )
            ready.set()
            while not proceed.wait(0.1):
                pass
            os._exit(137)

    recovery.record_execution = crash_after_reconciliation_audit

    result = recovery.recover_interrupted_actions()
    print("UNEXPECTED NORMAL RECOVERY RESULT:", result, flush=True)


def fresh_recovery_worker(queue):
    try:
        result = recovery.recover_interrupted_actions()
        queue.put(result)
    except Exception as exc:
        queue.put({"error": repr(exc)})


def main():
    print("=== RECOVERY AUDIT CRASH + NEW GENERATION FENCE TEST ===")
    print()

    original_state = STATE_PATH.read_bytes() if STATE_PATH.exists() else None
    audit_path = Path("state") / "audit.json"
    original_audit = audit_path.read_bytes() if audit_path.exists() else None

    ctx = mp.get_context("spawn")

    ready = ctx.Event()
    proceed = ctx.Event()

    try:
        print("1. PREPARING GENERATION 1 EXECUTED STATE:")
        write_state(
            ACTION,
            GEN1,
            "executed",
            "GENERATION-1-EXECUTED",
        )

        assert read_action()["status"] == "executed"
        assert read_action()["execution_generation"] == GEN1
        assert len(completion_events(GEN1)) == 0

        print(
            f"{ACTION} | status=executed | generation={GEN1}"
        )
        print("Completion audit events: 0")
        print("PASS")
        print()

        print("2. STARTING RECOVERY AGAINST GENERATION 1:")

        p = ctx.Process(
            target=crashing_recovery_worker,
            args=(ready, proceed, ACTION, GEN1),
        )
        p.start()

        assert ready.wait(10), "Recovery worker never reached crash injection."

        print(f"Recovery worker PID: {p.pid}")
        print("Recovery reached reconciliation audit write.")
        print("PASS")
        print()

        print("3. INSTALLING NEWER GENERATION 2:")

        write_state(
            ACTION,
            GEN2,
            "executed",
            "GENERATION-2-AUTHORITATIVE",
        )

        current = read_action()

        assert current["status"] == "executed"
        assert current["execution_generation"] == GEN2
        assert current["execution_result"] == "GENERATION-2-AUTHORITATIVE"

        print(
            f"{ACTION} | status=executed | generation={GEN2} "
            f"| result=GENERATION-2-AUTHORITATIVE"
        )
        print("Generation 2 installed.")
        print("PASS")
        print()

        print("4. ALLOWING GENERATION-1 RECOVERY PROCESS TO CRASH:")

        proceed.set()
        p.join(10)

        assert p.exitcode == 137, (
            f"Expected crash exitcode 137, got {p.exitcode}"
        )

        print(f"Recovery worker exitcode: {p.exitcode}")
        print("REAL PROCESS CRASH OCCURRED AFTER GENERATION-1 AUDIT.")
        print("PASS")
        print()

        print("5. VERIFYING GENERATION 2 SURVIVED:")

        current = read_action()

        assert current["status"] == "executed"
        assert current["execution_generation"] == GEN2
        assert current["execution_result"] == "GENERATION-2-AUTHORITATIVE"

        print(
            f"{ACTION} | status={current['status']} "
            f"| generation={current['execution_generation']} "
            f"| result={current['execution_result']}"
        )
        print("GENERATION 2 REMAINED AUTHORITATIVE.")
        print("PASS")
        print()

        print("6. VERIFYING GENERATION-SPECIFIC AUDIT FENCE:")

        gen1_events = completion_events(GEN1)
        gen2_events = completion_events(GEN2)

        assert len(gen1_events) == 1
        assert len(gen2_events) == 0

        print(f"Generation 1 completion events: {len(gen1_events)}")
        print(f"Generation 2 completion events: {len(gen2_events)}")
        print("GENERATION 1 AUDIT EXISTS EXACTLY ONCE.")
        print("GENERATION 2 HAS NOT BEEN FALSELY AUDITED.")
        print("PASS")
        print()

        print("7. FRESH-PROCESS RECOVERY OF CURRENT GENERATION:")

        queue = ctx.Queue()

        p2 = ctx.Process(
            target=fresh_recovery_worker,
            args=(queue,),
        )
        p2.start()
        p2.join(10)

        assert p2.exitcode == 0, (
            f"Fresh recovery process failed: {p2.exitcode}"
        )

        result = queue.get(timeout=5)

        if isinstance(result, dict) and "error" in result:
            raise AssertionError(result["error"])

        current = read_action()

        assert current["execution_generation"] == GEN2
        assert current["status"] == "executed"
        assert len(completion_events(GEN2)) == 1

        print("CURRENT RECOVERY RESULT:", result)
        print(
            f"Generation 2 completion events: "
            f"{len(completion_events(GEN2))}"
        )
        print("CURRENT GENERATION RECONCILED EXACTLY ONCE.")
        print("PASS")
        print()

        print("8. SECOND RECOVERY / IDEMPOTENCY:")

        second = recovery.recover_interrupted_actions()

        assert second == []
        assert len(completion_events(GEN1)) == 1
        assert len(completion_events(GEN2)) == 1

        print("SECOND RECOVERY RESULT:", second)
        print("Generation 1 completion events:", len(completion_events(GEN1)))
        print("Generation 2 completion events:", len(completion_events(GEN2)))
        print("NO DUPLICATE AUDIT WAS CREATED.")
        print("PASS")
        print()

        print("9. FINAL FRESH-PROCESS CONSISTENCY:")

        fresh = read_action()

        assert fresh["execution_generation"] == GEN2
        assert fresh["status"] == "executed"
        assert fresh["execution_result"] == "GENERATION-2-AUTHORITATIVE"

        assert len(completion_events(GEN1)) == 1
        assert len(completion_events(GEN2)) == 1

        print(
            f"{ACTION} | status={fresh['status']} "
            f"| generation={fresh['execution_generation']} "
            f"| result={fresh['execution_result']}"
        )
        print("Generation 1 audits:", len(completion_events(GEN1)))
        print("Generation 2 audits:", len(completion_events(GEN2)))
        print("FRESH PROCESS OBSERVED CONSISTENT STATE + AUDIT.")
        print("PASS")
        print()

        print("10. FINAL HARD INVARIANTS:")
        print("REAL PROCESS CRASH OCCURRED AFTER GENERATION-1 AUDIT")
        print("GENERATION 1 AUDIT REMAINED GENERATION-SPECIFIC")
        print("GENERATION 2 REPLACED GENERATION 1")
        print("GENERATION 2 REMAINED AUTHORITATIVE")
        print("NO GENERATION-2 AUDIT WAS FABRICATED BY GENERATION 1")
        print("CURRENT GENERATION 2 RECEIVED EXACTLY ONE COMPLETION AUDIT")
        print("SECOND RECOVERY WAS IDEMPOTENT")
        print("NO DUPLICATE COMPLETION AUDIT EXISTS")
        print("FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT")
        print()
        print("RESULT: PASS")

    finally:
        if original_state is not None:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_bytes(original_state)
        elif STATE_PATH.exists():
            STATE_PATH.unlink()

        temp = STATE_PATH.with_suffix(".tmp")
        if temp.exists():
            temp.unlink()

        if original_audit is not None:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_bytes(original_audit)
        elif audit_path.exists():
            audit_path.unlink()


if __name__ == "__main__":
    main()
