from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
import uuid
from pathlib import Path

from judgment.lifecycle import begin_execution
from judgment.recovery import recover_interrupted_actions
from judgment.audit import load_audit


STATE_PATH = Path("state") / "latest.json"
AUDIT_PATH = Path("state") / "audit.json"


ACTION = f"audit-state-replacement-fence-{uuid.uuid4().hex[:8]}"


def write_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")

    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, STATE_PATH)


def worker(started):
    started.set()
    result = recover_interrupted_actions()
    print("RECOVERY WORKER RESULT:", result, flush=True)


def read_action():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        state = json.load(f)

    for action in state.get("actions", []):
        if action.get("action") == ACTION:
            return action

    raise AssertionError("Target action not found")


def matching_events(generation=None, event_type=None):
    events = load_audit()

    result = [
        e for e in events
        if isinstance(e, dict)
        and e.get("action") == ACTION
    ]

    if generation is not None:
        result = [
            e for e in result
            if e.get("execution_generation") == generation
        ]

    if event_type is not None:
        result = [
            e for e in result
            if e.get("event") == event_type
        ]

    return result


def main():
    print("=== AUDIT + STATE REPLACEMENT GENERATION FENCE TEST ===\n")

    # Clean target from previous runs.
    state = {"actions": []}
    if STATE_PATH.exists():
        try:
            with STATE_PATH.open("r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {"actions": []}

    state["actions"] = [
        a for a in state.get("actions", [])
        if a.get("action") != ACTION
    ]
    state["actions"].append({
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_generation": 0,
        "execution_result": None,
    })
    write_state(state)

    print("1. PREPARING GENERATION 1:")
    started = begin_execution(ACTION)
    assert started["status"] == "executing"

    gen1 = started["execution_generation"]

    # Make generation 1 stale.
    state = json.load(STATE_PATH.open("r", encoding="utf-8"))
    for action in state["actions"]:
        if action.get("action") == ACTION:
            action["execution_started_at"] = "2000-01-01T00:00:00+00:00"

    write_state(state)

    print(
        f"{ACTION} | status=executing | generation={gen1}"
    )
    print("PASS\n")

    print("2. STARTING RECOVERY WORKER:")

    ctx = mp.get_context("spawn")
    started_event = ctx.Event()

    p = ctx.Process(
        target=worker,
        args=(started_event,),
    )

    p.start()
    print(f"Recovery worker PID: {p.pid}")

    started_event.wait(timeout=10)

    # Give recovery enough time to load generation 1.
    time.sleep(0.15)

    print("PASS\n")

    print("3. INSTALLING GENERATION 2 BEFORE RECOVERY FINISHES:")

    # Replace generation 1 with a completely newer executed generation.
    state = json.load(STATE_PATH.open("r", encoding="utf-8"))

    found = False

    for action in state["actions"]:
        if action.get("action") == ACTION:
            action.update({
                "status": "executed",
                "execution_result": "GENERATION-2-AUTHORITATIVE",
                "execution_generation": gen1 + 1,
                "execution_completed_at": "2099-01-01T00:00:01+00:00",
            })
            found = True

    assert found
    write_state(state)

    gen2 = gen1 + 1

    current = read_action()

    print(
        f"{ACTION} | status={current['status']} | "
        f"generation={current['execution_generation']} | "
        f"result={current['execution_result']}"
    )
    print("Generation 2 installed.")
    print("PASS\n")

    print("4. WAITING FOR STALE RECOVERY:")

    p.join(timeout=15)

    if p.is_alive():
        p.terminate()
        p.join()
        raise AssertionError("Recovery worker did not terminate")

    print("Recovery worker exitcode:", p.exitcode)
    assert p.exitcode == 0
    print("PASS\n")

    print("5. VERIFYING GENERATION 2 SURVIVED:")

    current = read_action()

    print(
        f"{ACTION} | status={current['status']} | "
        f"generation={current['execution_generation']} | "
        f"result={current['execution_result']}"
    )

    assert current["status"] == "executed"
    assert current["execution_generation"] == gen2
    assert current["execution_result"] == "GENERATION-2-AUTHORITATIVE"

    print("GENERATION 2 REMAINED AUTHORITATIVE.")
    print("PASS\n")

    print("6. VERIFYING GENERATION-SPECIFIC AUDIT FENCE:")

    gen1_recovery = matching_events(gen1, "recovery-interrupted")
    gen1_completion = matching_events(gen1, "execution-completed")
    gen2_completion = matching_events(gen2, "execution-completed")

    print("Generation 1 recovery events:", len(gen1_recovery))
    print("Generation 1 completion events:", len(gen1_completion))
    print("Generation 2 completion events:", len(gen2_completion))

    assert len(gen1_completion) == 0
    assert len(gen2_completion) <= 1

    print("NO STALE GENERATION-1 COMPLETION WAS CREATED.")
    print("PASS\n")

    print("7. RECONCILING CURRENT GENERATION:")

    recovery_result = recover_interrupted_actions()
    print("CURRENT RECOVERY RESULT:", recovery_result)

    gen2_completion = matching_events(gen2, "execution-completed")

    print(
        "Generation 2 completion events:",
        len(gen2_completion)
    )

    assert len(gen2_completion) == 1

    print("CURRENT GENERATION HAS EXACTLY ONE COMPLETION AUDIT.")
    print("PASS\n")

    print("8. SECOND RECOVERY / DUPLICATION CHECK:")

    second = recover_interrupted_actions()

    print("SECOND RECOVERY RESULT:", second)

    gen2_completion_after = matching_events(
        gen2,
        "execution-completed",
    )

    assert second == []
    assert len(gen2_completion_after) == 1

    print("NO DUPLICATE CURRENT-GENERATION AUDIT.")
    print("PASS\n")

    print("9. FRESH-PROCESS CONSISTENCY:")

    fresh = read_action()

    print(
        f"{ACTION} | status={fresh['status']} | "
        f"generation={fresh['execution_generation']} | "
        f"result={fresh['execution_result']}"
    )

    assert fresh["execution_generation"] == gen2
    assert fresh["execution_result"] == "GENERATION-2-AUTHORITATIVE"

    print("FRESH PROCESS OBSERVED GENERATION 2.")
    print("PASS\n")

    print("10. FINAL HARD INVARIANTS:")

    print("STALE RECOVERY COULD NOT REASSERT GENERATION 1")
    print("GENERATION 2 REMAINED AUTHORITATIVE")
    print("NO STALE COMPLETION AUDIT WAS FABRICATED")
    print("CURRENT GENERATION RECEIVED EXACTLY ONE COMPLETION AUDIT")
    print("SECOND RECOVERY WAS IDEMPOTENT")
    print("FRESH PROCESS OBSERVED THE SAME STATE")
    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
