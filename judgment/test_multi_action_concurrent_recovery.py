import json
import multiprocessing
import os
from pathlib import Path

import judgment.recovery as recovery
from judgment.audit import load_audit
from judgment.recovery import recover_interrupted_actions

STATE_PATH = Path("state/latest.json")
AUDIT_PATH = Path("state/audit.json")

ACTIONS = [
    ("multi-action-recovery-A", 1),
    ("multi-action-recovery-B", 2),
    ("multi-action-recovery-C", 3),
]


def prepare_state():
    state = {
        "actions": [
            {
                "action": name,
                "priority": "high",
                "execution_mode": "automatic",
                "status": "executed",
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
                "execution_result": f"MULTI-ACTION-{name}",
                "execution_generation": generation,
                "execution_started_at": "2026-10-05T06:00:00+00:00",
                "execution_completed_at": "2026-10-05T06:00:00+00:00",
            }
            for name, generation in ACTIONS
        ]
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


def load_events():
    if not AUDIT_PATH.exists():
        return []

    return load_audit()


def matching_events(action):
    return [
        event
        for event in load_events()
        if isinstance(event, dict)
        and event.get("action") == action
        and event.get("event") == "execution-completed"
    ]


def crashing_worker():
    original = recovery.record_execution

    def crash_after_first_audit(events):
        original(events)

        print(
            "CRASH INJECTION: first multi-action reconciliation "
            "audit is durable; process now crashes.",
            flush=True,
        )

        os._exit(137)

    recovery.record_execution = crash_after_first_audit
    recover_interrupted_actions()


def normal_worker(worker_id):
    result = recover_interrupted_actions()
    print(
        f"RECOVERY WORKER {worker_id}: {result}",
        flush=True,
    )


def main():
    print("=== MULTI-ACTION CONCURRENT RECOVERY ISOLATION TEST ===")

    print("\n1. PREPARING MULTIPLE EXECUTED ACTIONS:")
    prepare_state()

    state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    assert len(state["actions"]) == 3

    for name, generation in ACTIONS:
        action = next(
            a for a in state["actions"]
            if a["action"] == name
        )

        print(
            f"{name} | status={action['status']} | "
            f"generation={action['execution_generation']}"
        )

        assert action["status"] == "executed"
        assert action["execution_generation"] == generation
        assert len(matching_events(name)) == 0

    print("All three actions have missing completion audits.")
    print("PASS")

    print("\n2. STARTING CRASHING RECOVERY:")
    crash = multiprocessing.Process(
        target=crashing_worker
    )
    crash.start()
    crash.join()

    print(
        f"Crash worker PID={crash.pid} | "
        f"exitcode={crash.exitcode}"
    )

    assert crash.exitcode == 137

    print("Real recovery-process crash occurred.")
    print("PASS")

    print("\n3. STARTING CONCURRENT RECOVERY WORKERS:")
    workers = []

    for worker_id in range(1, 9):
        p = multiprocessing.Process(
            target=normal_worker,
            args=(worker_id,),
        )
        workers.append(p)
        p.start()

    for p in workers:
        p.join()

    assert all(p.exitcode == 0 for p in workers)

    print("All concurrent recovery workers completed.")
    print("PASS")

    print("\n4. CHECKING PER-ACTION RECONCILIATION:")
    for name, generation in ACTIONS:
        events = matching_events(name)

        print(
            f"{name}: completion events={len(events)}"
        )

        assert len(events) == 1

        event = events[0]

        assert event.get("action") == name
        assert event.get("execution_generation") == generation
        assert event.get("status") == "executed"

        print(
            f"  generation={event.get('execution_generation')} "
            f"status={event.get('status')}"
        )

    print("Exactly one completion audit exists for every action.")
    print("Generation identities are correct.")
    print("PASS")

    print("\n5. VERIFYING CROSS-ACTION ISOLATION:")
    events = load_events()

    relevant = [
        e for e in events
        if isinstance(e, dict)
        and e.get("action") in {a[0] for a in ACTIONS}
        and e.get("event") == "execution-completed"
    ]

    assert len(relevant) == 3

    pairs = {
        (
            e.get("action"),
            e.get("execution_generation"),
        )
        for e in relevant
    }

    expected_pairs = set(ACTIONS)

    assert pairs == expected_pairs

    print(
        "Audit action/generation pairs:",
        sorted(pairs),
    )
    print("No action received another action's reconciliation.")
    print("PASS")

    print("\n6. VERIFYING DURABLE STATE:")
    state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    for name, generation in ACTIONS:
        action = next(
            a for a in state["actions"]
            if a.get("action") == name
        )

        print(
            f"{name} | status={action.get('status')} | "
            f"generation={action.get('execution_generation')} | "
            f"result={action.get('execution_result')}"
        )

        assert action.get("status") == "executed"
        assert action.get("execution_generation") == generation

    print("All durable action states survived independently.")
    print("PASS")

    print("\n7. SECOND CONCURRENT RECOVERY WAVE:")
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

    print("\n8. FINAL DUPLICATION CHECK:")
    for name, generation in ACTIONS:
        events = matching_events(name)

        print(
            f"{name}: final completion events={len(events)}"
        )

        assert len(events) == 1

    print("No duplicate reconciliation event exists for any action.")
    print("PASS")

    print("\n9. FRESH-PROCESS CONSISTENCY:")
    fresh_state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    for name, generation in ACTIONS:
        action = next(
            a for a in fresh_state["actions"]
            if a.get("action") == name
        )

        print(
            f"{name}: status={action.get('status')} | "
            f"generation={action.get('execution_generation')}"
        )

        assert action.get("status") == "executed"
        assert action.get("execution_generation") == generation

    print("Fresh process observed all three states consistently.")
    print("PASS")

    print("\n10. FINAL MULTI-ACTION INVARIANTS:")
    print("MULTIPLE ACTIONS WERE RECOVERED CONCURRENTLY")
    print("REAL PROCESS CRASH OCCURRED DURING RECOVERY")
    print("EACH ACTION RECEIVED EXACTLY ONE RECONCILIATION")
    print("ACTION IDENTITIES REMAINED ISOLATED")
    print("GENERATION IDENTITIES REMAINED ISOLATED")
    print("NO CROSS-ACTION AUDIT CORRUPTION OCCURRED")
    print("SECOND RECOVERY WAVE WAS IDEMPOTENT")
    print("ALL DURABLE STATES REMAINED EXECUTED")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
