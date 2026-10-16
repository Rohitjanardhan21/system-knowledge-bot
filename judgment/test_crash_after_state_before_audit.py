from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path

import judgment.lifecycle as lifecycle
from judgment.audit import load_audit
from judgment.lifecycle import begin_execution, complete_execution


STATE_PATH = Path("state") / "latest.json"
ACTION = "free-disk-space"


def load_state():
    return json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )


def get_action():
    state = load_state()

    return next(
        action
        for action in state["actions"]
        if action.get("action") == ACTION
    )


def prepare_state():
    state = load_state()
    audit_generations = [
        event["execution_generation"]
        for event in load_audit()
        if (
            isinstance(event, dict)
            and event.get("action") == ACTION
            and isinstance(event.get("execution_generation"), int)
            and not isinstance(event.get("execution_generation"), bool)
        )
    ]

    target = next(
        (
            action
            for action in state["actions"]
            if action.get("action") == ACTION
        ),
        None,
    )

    if target is None:
        target = {
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
        }
        state.setdefault("actions", []).append(target)

    target["status"] = "approved"
    target["retry_count"] = 0
    target["max_retries"] = 2
    target["escalation_required"] = False
    target["execution_result"] = None

    current_generation = target.get("execution_generation", 0)
    if (
        not isinstance(current_generation, int)
        or isinstance(current_generation, bool)
        or current_generation < 0
    ):
        current_generation = 0
    target["execution_generation"] = max(
        current_generation,
        max(audit_generations, default=0),
    )

    target.pop("execution_started_at", None)
    target.pop("execution_completed_at", None)

    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def crash_after_state_persist(results):
    """
    This function replaces lifecycle.record_execution()
    inside the child process.

    complete_execution() has already called _persist_action()
    immediately before reaching this function.

    Therefore the child dies after lifecycle state persistence
    but before any audit event can be written.
    """

    print(
        "CRASH INJECTION: lifecycle state has already "
        "been persisted; killing process before audit.",
        flush=True,
    )

    os._exit(137)


def crashing_worker(generation):
    lifecycle.record_execution = crash_after_state_persist

    result = complete_execution(
        ACTION,
        success=True,
        result="CRASH-BEFORE-AUDIT",
        execution_generation=generation,
    )

    print(
        "UNEXPECTED COMPLETION:",
        result,
        flush=True,
    )


def main():
    multiprocessing.freeze_support()

    print()
    print("=== CRASH AFTER STATE PERSIST / BEFORE AUDIT TEST ===")
    print()

    # ------------------------------------------------------------
    # 1. CLEAN APPROVED STATE
    # ------------------------------------------------------------
    print("1. PREPARING CLEAN APPROVED STATE:")

    prepare_state()

    action = get_action()

    print(
        ACTION,
        "| status =", action["status"],
        "| retry_count =", action["retry_count"],
    )

    assert action["status"] == "approved"
    assert action["retry_count"] == 0

    print("PASS")

    # ------------------------------------------------------------
    # 2. BEGIN EXECUTION
    # ------------------------------------------------------------
    print()
    print("2. STARTING EXECUTION:")

    audit_before = load_audit()

    started = begin_execution(ACTION)

    print("START:", started)

    assert started["status"] == "executing"

    generation = started["execution_generation"]

    print("Generation:", generation)
    print("PASS")

    # ------------------------------------------------------------
    # 3. CRASHING CHILD
    # ------------------------------------------------------------
    print()
    print("3. CRASHING AFTER STATE PERSISTENCE:")

    process = multiprocessing.Process(
        target=crashing_worker,
        args=(generation,),
    )

    process.start()
    process.join()

    print(
        "Child PID:",
        process.pid,
        "| exitcode:",
        process.exitcode,
    )

    assert process.exitcode == 137

    print(
        "Real child-process crash occurred "
        "at the state→audit boundary."
    )
    print("PASS")

    # ------------------------------------------------------------
    # 4. DURABLE STATE MUST HAVE SURVIVED
    # ------------------------------------------------------------
    print()
    print("4. CHECKING DURABLE LIFECYCLE STATE:")

    action = get_action()

    print(
        ACTION,
        "| status =", action["status"],
        "| result =", action.get("execution_result"),
        "| generation =", action.get("execution_generation"),
    )

    assert action["status"] == "executed"
    assert action["execution_generation"] == generation
    assert action["execution_result"] == "CRASH-BEFORE-AUDIT"

    print(
        "Lifecycle state survived the process crash."
    )
    print("PASS")

    # ------------------------------------------------------------
    # 5. AUDIT MUST NOT CLAIM COMPLETION
    # ------------------------------------------------------------
    print()
    print("5. CHECKING AUDIT:")

    audit_after = load_audit()

    new_events = audit_after[len(audit_before):]

    completion_events = [
        event
        for event in new_events
        if (
            event.get("action") == ACTION
            and event.get("event") == "execution-completed"
            and event.get("result") == "CRASH-BEFORE-AUDIT"
            and event.get("execution_generation") == generation
        )
    ]

    print(
        "Matching completion events:",
        len(completion_events),
    )

    assert len(completion_events) == 0

    print(
        "Audit correctly contains no fabricated "
        "completion event."
    )
    print("PASS")

    # ------------------------------------------------------------
    # 6. FRESH-PROCESS RECOVERY
    # ------------------------------------------------------------
    print()
    print("6. FRESH-PROCESS RECOVERY:")

    recovery_code = """
from judgment.recovery import recover_interrupted_actions

result = recover_interrupted_actions()
print("RECOVERY RESULT:", result)
"""

    recovery = subprocess.run(
        [
            sys.executable,
            "-c",
            recovery_code,
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )

    print(recovery.stdout)

    if recovery.returncode != 0:
        print(recovery.stderr)
        raise SystemExit(recovery.returncode)

    print("Fresh process recovery completed.")
    print("PASS")

    # ------------------------------------------------------------
    # 7. FINAL STATE
    # ------------------------------------------------------------
    print()
    print("7. FINAL DURABLE STATE:")

    final_action = get_action()

    print(
        ACTION,
        "| status =", final_action["status"],
        "| result =", final_action.get("execution_result"),
        "| generation =", final_action.get(
            "execution_generation"
        ),
    )

    assert final_action["status"] == "executed"
    assert final_action["execution_generation"] == generation

    print("PASS")

    # ------------------------------------------------------------
    # 8. FINAL AUDIT
    # ------------------------------------------------------------
    print()
    print("8. FINAL AUDIT:")

    final_audit = load_audit()

    final_matches = [
        event
        for event in final_audit
        if (
            event.get("action") == ACTION
            and event.get("event") == "execution-completed"
            and event.get("result") == "CRASH-BEFORE-AUDIT"
            and event.get("execution_generation") == generation
        )
    ]

    print(
        "CRASH-BEFORE-AUDIT completion events:",
        len(final_matches),
    )

    assert len(final_matches) == 1
    assert final_matches[0].get("recovered") is True

    print("PASS")

    # ------------------------------------------------------------
    # 9. FINAL INVARIANTS
    # ------------------------------------------------------------
    print()
    print("9. FINAL INVARIANTS:")

    print("REAL PROCESS CRASH OCCURRED")
    print("LIFECYCLE STATE WAS DURABLE")
    print("RECOVERY RECONCILED THE MISSING COMPLETION AUDIT")
    print("GENERATION REMAINED STABLE")
    print("FRESH-PROCESS RECOVERY COMPLETED")
    print("EXACTLY ONE COMPLETION EVENT EXISTS FOR THE GENERATION")

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
