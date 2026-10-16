import json
import threading
import time
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.audit import load_audit
from judgment.lifecycle import (
    begin_execution,
    complete_execution,
    retry_failed_action,
    run_execution_side_effect,
    state_lock,
)

STATE_PATH = Path("state/latest.json")
ACTION = "free-disk-space"

SANDBOX = Path("state/test_reauthorization_stale_completion_race")
FILE_A = SANDBOX / "A.txt"
FILE_B = SANDBOX / "B.txt"
FILE_C = SANDBOX / "C.txt"


def load_state():
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def action_state():
    state = load_state()
    return next(
        a for a in state["actions"]
        if a.get("action") == ACTION
    )


def audit_events():
    return load_audit()


def reset_durable_state():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "actions": [{
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "approved",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": None,
            "execution_generation": 0
        }]
    }

    with state_lock():
        STATE_PATH.write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )


def prepare():
    SANDBOX.mkdir(parents=True, exist_ok=True)

    for f in (FILE_A, FILE_B, FILE_C):
        f.write_text(f"initial-{f.name}", encoding="utf-8")


def cleanup():
    for f in (FILE_A, FILE_B, FILE_C):
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass

    try:
        SANDBOX.rmdir()
    except OSError:
        pass


print()
print("=== REAUTHORIZATION + STALE WORKER + CONCURRENT COMPLETION RACE TEST ===")
print()

reset_durable_state()
prepare()
before_events = audit_events()

try:
    # ------------------------------------------------------------
    # 1. INITIAL STATE
    # ------------------------------------------------------------

    print("1. INITIAL REAL-WORLD STATE:")
    print("A:", FILE_A.exists())
    print("B:", FILE_B.exists())
    print("C:", FILE_C.exists())

    assert FILE_A.exists()
    assert FILE_B.exists()
    assert FILE_C.exists()

    print("PASS")
    print()

    # ------------------------------------------------------------
    # 2. INITIAL AUTHORIZATION
    # ------------------------------------------------------------

    state = action_state()

    print("2. INITIAL AUTHORIZATION:")
    print(
        ACTION,
        "| status =", state["status"],
        "| retry_count =", state["retry_count"],
    )

    assert state["status"] == "approved"

    print("PASS")
    print()

    # ------------------------------------------------------------
    # 3. WORKER A
    # ------------------------------------------------------------

    print("3. WORKER A STARTS:")

    worker_a = begin_execution({"action": ACTION})

    print("WORKER A:", worker_a)

    assert worker_a["status"] == "executing"

    generation_a = worker_a["execution_generation"]

    print("Generation A:", generation_a)
    print("PASS")
    print()

    # ------------------------------------------------------------
    # 4. WORKER A SIDE EFFECT
    # ------------------------------------------------------------

    print("4. WORKER A PRODUCES PARTIAL SIDE EFFECT:")

    side_a = run_execution_side_effect(
        {"action": ACTION},
        generation_a,
        lambda: (
            FILE_A.unlink(),
            "deleted-a",
        )[1],
    )

    print("SIDE EFFECT:", side_a)

    assert side_a["status"] == "allowed"
    assert not FILE_A.exists()
    assert FILE_B.exists()
    assert FILE_C.exists()

    print("A exists:", FILE_A.exists())
    print("B exists:", FILE_B.exists())
    print("C exists:", FILE_C.exists())
    print("PASS")
    print()

    # ------------------------------------------------------------
    # 5. AUTHORIZATION REVOCATION
    #
    # Direct durable mutation is intentional here: this test is
    # exercising the lifecycle after an authorization decision.
    # ------------------------------------------------------------

    print("5. AUTHORIZATION IS REVOKED:")

    with state_lock():
        state = load_state()

        for stored in state["actions"]:
            if stored.get("action") == ACTION:
                stored["status"] = "rejected"
                stored["execution_result"] = (
                    "authorization-revoked-after-side-effect"
                )

        STATE_PATH.write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )

    state = action_state()

    print(
        ACTION,
        "| status =", state["status"],
        "| result =", state.get("execution_result"),
    )

    assert state["status"] == "rejected"

    print("PASS")
    print()

    # ------------------------------------------------------------
    # 6. STALE WORKER A COMPLETION
    # ------------------------------------------------------------

    print("6. STALE WORKER A ATTEMPTS COMPLETION:")

    stale_completion = complete_execution(
        {"action": ACTION},
        success=True,
        result="STALE-A-SUCCESS",
        execution_generation=generation_a,
    )

    print("STALE COMPLETION:", stale_completion)

    assert stale_completion["status"] == "blocked"

    print("Worker A could not manufacture success.")
    print("PASS")
    print()

    # ------------------------------------------------------------
    # 7. RE-AUTHORIZATION
    #
    # Explicitly restore authorization and reset only the
    # authorization state. Generation must advance on execution.
    # ------------------------------------------------------------

    print("7. EXPLICIT RE-AUTHORIZATION:")

    with state_lock():
        state = load_state()

        for stored in state["actions"]:
            if stored.get("action") == ACTION:
                stored["status"] = "approved"
                stored["execution_result"] = None

        STATE_PATH.write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )

    state = action_state()

    print(
        ACTION,
        "| status =", state["status"],
        "| retry_count =", state["retry_count"],
        "| generation =", state.get("execution_generation"),
    )

    assert state["status"] == "approved"

    print("PASS")
    print()

    # ------------------------------------------------------------
    # 8. WORKER B
    # ------------------------------------------------------------

    print("8. WORKER B STARTS NEW GENERATION:")

    worker_b = begin_execution({"action": ACTION})

    print("WORKER B:", worker_b)

    assert worker_b["status"] == "executing"

    generation_b = worker_b["execution_generation"]

    print(
        "Generation A:", generation_a,
        "| Generation B:", generation_b,
    )

    assert generation_b > generation_a

    print("New authorization received a new execution generation.")
    print("PASS")
    print()

    # ------------------------------------------------------------
    # 9. EXTERNAL MUTATION
    # ------------------------------------------------------------

    print("9. EXTERNAL PROCESS MUTATES WORLD:")

    if FILE_B.exists():
        FILE_B.unlink()

    print("A:", FILE_A.exists())
    print("B:", FILE_B.exists())
    print("C:", FILE_C.exists())

    assert not FILE_A.exists()
    assert not FILE_B.exists()
    assert FILE_C.exists()

    print("PASS")
    print()

    # ------------------------------------------------------------
    # 10. STALE WORKER A SIDE EFFECT
    # ------------------------------------------------------------

    print("10. STALE WORKER A ATTEMPTS SIDE EFFECT:")

    stale_side_effect = run_execution_side_effect(
        {"action": ACTION},
        generation_a,
        lambda: (
            FILE_C.unlink(),
            "STALE-DELETED-C",
        )[1],
    )

    print("STALE SIDE EFFECT:", stale_side_effect)

    assert stale_side_effect["status"] == "blocked"
    assert stale_side_effect["result"] == "stale-execution-generation"

    assert FILE_C.exists()

    print("C exists after stale attempt:", FILE_C.exists())
    print("PASS")
    print()

    # ------------------------------------------------------------
    # 11. CONCURRENT WORKER B COMPLETION RACE
    # ------------------------------------------------------------

    print("11. CONCURRENT WORKER B COMPLETION RACE:")

    results = []
    errors = []
    barrier = threading.Barrier(8)

    def completion_worker(worker_id):
        try:
            barrier.wait()

            result = complete_execution(
                {"action": ACTION},
                success=True,
                result=f"WORKER-B-{worker_id}-SUCCESS",
                execution_generation=generation_b,
            )

            results.append((worker_id, result))

        except Exception as exc:
            errors.append((worker_id, repr(exc)))

    threads = [
        threading.Thread(
            target=completion_worker,
            args=(i,),
            name=f"worker-b-{i}",
        )
        for i in range(1, 9)
    ]

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    for item in sorted(results):
        print(item)

    for item in errors:
        print("ERROR:", item)

    assert not errors

    executed = [
        result
        for _, result in results
        if result.get("status") == "executed"
    ]

    blocked = [
        result
        for _, result in results
        if result.get("status") == "blocked"
    ]

    print()
    print("Executed:", len(executed))
    print("Blocked:", len(blocked))
    print("Errors:", len(errors))

    assert len(executed) == 1
    assert len(blocked) == 7

    print("Exactly ONE Worker-B completion won.")
    print("All competing completions were blocked.")
    print("PASS")
    print()

    # ------------------------------------------------------------
    # 12. DURABLE STATE
    # ------------------------------------------------------------

    print("12. FINAL DURABLE STATE:")

    state = action_state()

    print(
        ACTION,
        "| status =", state["status"],
        "| result =", state.get("execution_result"),
        "| retry_count =", state["retry_count"],
        "| generation =", state.get("execution_generation"),
    )

    assert state["status"] == "executed"
    assert state["execution_generation"] == generation_b
    assert state["retry_count"] == 0

    print("PASS")
    print()

    # ------------------------------------------------------------
    # 13. REAL-WORLD STATE
    # ------------------------------------------------------------

    print("13. FINAL REAL-WORLD STATE:")

    print("A:", FILE_A.exists())
    print("B:", FILE_B.exists())
    print("C:", FILE_C.exists())

    assert not FILE_A.exists()
    assert not FILE_B.exists()
    assert FILE_C.exists()

    print("Stale Worker A could not delete C.")
    print("External mutation of B was preserved.")
    print("PASS")
    print()

    # ------------------------------------------------------------
    # 14. AUDIT
    # ------------------------------------------------------------

    print("14. AUDIT:")

    all_events = audit_events()
    events = [
        event
        for event in all_events[len(before_events):]
        if event.get("action") == ACTION
    ]

    for event in events:
        print(
            event.get("event"),
            "|",
            event.get("status"),
            "|",
            event.get("result"),
        )

    completions = [
        event for event in events
        if (
            event.get("event") == "execution-completed"
            and str(event.get("result", "")).startswith("WORKER-B-")
        )
    ]

    assert len(completions) == 1

    print("Exactly one durable execution-completed event exists.")
    print("PASS")
    print()

    # ------------------------------------------------------------
    # 15. HARD INVARIANTS
    # ------------------------------------------------------------

    print("15. FINAL HARD INVARIANTS:")
    print("INITIAL WORKER A HAD A VALID GENERATION")
    print("WORKER A PRODUCED A REAL-WORLD SIDE EFFECT")
    print("AUTHORIZATION WAS REVOKED")
    print("WORKER A COULD NOT MANUFACTURE SUCCESS")
    print("RE-AUTHORIZATION CREATED A NEW GENERATION")
    print("WORKER B BECAME THE CURRENT OWNER")
    print("EXTERNAL MUTATION WAS PRESERVED")
    print("STALE WORKER A COULD NOT MUTATE THE WORLD")
    print("EXACTLY ONE WORKER-B COMPLETION WON")
    print("ALL COMPETING COMPLETIONS WERE BLOCKED")
    print("DURABLE STATE MATCHED GENERATION B")
    print("AUDIT CONTAINED EXACTLY ONE SUCCESSFUL COMPLETION")
    print()
    print("RESULT: PASS")

finally:
    cleanup()
