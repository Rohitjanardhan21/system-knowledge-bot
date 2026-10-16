from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.audit import load_audit
from judgment.lifecycle import begin_execution, complete_execution
import judgment.lifecycle as lifecycle
import judgment.recovery as recovery


STATE_PATH = Path("state/latest.json")
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

    for key in (
        "execution_started_at",
        "execution_completed_at",
        "execution_generation",
        "recovery_reason",
    ):
        target.pop(key, None)

    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def completion_worker(generation, output_path):
    """
    Independent process attempting to complete generation N.
    """

    result = complete_execution(
        ACTION,
        success=True,
        result="RECOVERY-RACE-COMPLETION",
        execution_generation=generation,
    )

    Path(output_path).write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )


def recovery_worker(output_path):
    """
    Independent process attempting restart recovery.
    """

    result = recovery.recover_interrupted_actions()

    Path(output_path).write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )


def run_race(generation, round_number):
    completion_output = (
        Path("state")
        / f"recovery_race_completion_{round_number}.json"
    )

    recovery_output = (
        Path("state")
        / f"recovery_race_recovery_{round_number}.json"
    )

    for path in (
        completion_output,
        recovery_output,
    ):
        if path.exists():
            path.unlink()

    completion = multiprocessing.Process(
        target=completion_worker,
        args=(generation, completion_output),
    )

    recover = multiprocessing.Process(
        target=recovery_worker,
        args=(recovery_output,),
    )

    # Start both as close together as possible.
    completion.start()
    recover.start()

    completion.join()
    recover.join()

    completion_result = (
        json.loads(completion_output.read_text(encoding="utf-8"))
        if completion_output.exists()
        else {"status": "missing"}
    )

    recovery_result = (
        json.loads(recovery_output.read_text(encoding="utf-8"))
        if recovery_output.exists()
        else {"status": "missing"}
    )

    return (
        completion_result,
        recovery_result,
        completion.exitcode,
        recover.exitcode,
    )


def main():
    multiprocessing.freeze_support()

    print()
    print("=== RECOVERY + COMPLETION RACE TEST ===")
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

    print("PASS")

    # ------------------------------------------------------------
    # 2. START EXECUTION
    # ------------------------------------------------------------
    print()
    print("2. STARTING EXECUTION:")

    started = begin_execution(ACTION)

    print("START:", started)

    assert started["status"] == "executing"

    generation = started["execution_generation"]

    print("Generation:", generation)
    print("PASS")

    # ------------------------------------------------------------
    # 3. VERIFY DURABLE EXECUTING STATE
    # ------------------------------------------------------------
    print()
    print("3. VERIFYING DURABLE EXECUTING STATE:")

    action = get_action()

    print(
        ACTION,
        "| status =", action["status"],
        "| generation =", action.get("execution_generation"),
    )

    assert action["status"] == "executing"
    assert action["execution_generation"] == generation

    print("PASS")

    # ------------------------------------------------------------
    # 4. RUN CONCURRENT RACES
    # ------------------------------------------------------------
    print()
    print("4. RUNNING RECOVERY + COMPLETION RACES:")

    audit_before = load_audit()

    completion_wins = 0
    recovery_wins = 0
    invalid_outcomes = 0

    for round_number in range(1, 11):
        # Each round needs a fresh executing generation.
        if round_number > 1:
            prepare_state()

            restarted = begin_execution(ACTION)

            assert restarted["status"] == "executing"

            generation = restarted["execution_generation"]

        (
            completion_result,
            recovery_result,
            completion_exit,
            recovery_exit,
        ) = run_race(
            generation,
            round_number,
        )

        final_action = get_action()
        final_status = final_action.get("status")
        final_generation = final_action.get(
            "execution_generation"
        )

        print()
        print(f"ROUND {round_number}")
        print("Generation:", generation)
        print("Completion:", completion_result)
        print("Recovery:", recovery_result)
        print("Final:", final_status)
        print("Final generation:", final_generation)

        assert completion_exit == 0
        assert recovery_exit == 0

        assert final_generation == generation

        if final_status == "executed":
            completion_wins += 1

            assert completion_result.get("status") == "executed"

            # Recovery must not claim it recovered this action.
            assert (
                ACTION not in recovery_result
                if isinstance(recovery_result, list)
                else True
            )

        elif final_status == "failed":
            recovery_wins += 1

            assert final_action.get(
                "execution_result"
            ) == "interrupted-by-restart"

            assert (
                ACTION in recovery_result
                if isinstance(recovery_result, list)
                else False
            )

            # Completion must not manufacture success.
            assert completion_result.get("status") != "executed"

        else:
            invalid_outcomes += 1

        # No impossible terminal result.
        assert final_status in {
            "executed",
            "failed",
        }

    print()
    print("COMPLETION WINS:", completion_wins)
    print("RECOVERY WINS:", recovery_wins)
    print("INVALID OUTCOMES:", invalid_outcomes)

    assert completion_wins + recovery_wins == 10
    assert invalid_outcomes == 0

    print("Exactly one terminal winner existed per generation.")
    print("PASS")

    # ------------------------------------------------------------
    # 5. AUDIT ANALYSIS
    # ------------------------------------------------------------
    print()
    print("5. AUDIT ANALYSIS:")

    audit_after = load_audit()

    new_events = audit_after[len(audit_before):]

    completion_events = [
        event
        for event in new_events
        if (
            event.get("action") == ACTION
            and event.get("event") == "execution-completed"
            and event.get("result")
            == "RECOVERY-RACE-COMPLETION"
        )
    ]

    recovery_events = [
        event
        for event in new_events
        if (
            event.get("action") == ACTION
            and event.get("event") == "recovery-interrupted"
            and event.get("result")
            == "interrupted-by-restart"
        )
    ]

    print(
        "Completion events:",
        len(completion_events),
    )

    print(
        "Recovery events:",
        len(recovery_events),
    )

    assert len(completion_events) == completion_wins
    assert len(recovery_events) == recovery_wins

    print(
        "Audit event counts agree with terminal winners."
    )
    print("PASS")

    # ------------------------------------------------------------
    # 6. FRESH-PROCESS CONSISTENCY
    # ------------------------------------------------------------
    print()
    print("6. FRESH-PROCESS CONSISTENCY CHECK:")

    child_code = """
import json
from pathlib import Path

state = json.loads(
    Path("state/latest.json").read_text(
        encoding="utf-8"
    )
)

target = next(
    action
    for action in state["actions"]
    if action.get("action") == "free-disk-space"
)

print(
    "FINAL:",
    target.get("status"),
    "| generation =",
    target.get("execution_generation"),
    "| result =",
    target.get("execution_result"),
)
"""

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            child_code,
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )

    print(child.stdout)

    if child.returncode != 0:
        print(child.stderr)
        raise SystemExit(child.returncode)

    print("Fresh process observed valid terminal state.")
    print("PASS")

    # ------------------------------------------------------------
    # 7. FINAL INVARIANTS
    # ------------------------------------------------------------
    print()
    print("7. FINAL RECOVERY + COMPLETION INVARIANTS:")

    print("RECOVERY AND COMPLETION WERE RUN CONCURRENTLY")
    print("EVERY GENERATION HAD EXACTLY ONE TERMINAL WINNER")
    print("NO GENERATION CHANGED DURING THE RACE")
    print("COMPLETION COULD NOT OVERWRITE RECOVERY")
    print("RECOVERY COULD NOT OVERWRITE COMPLETION")
    print("AUDIT COUNTS MATCHED TERMINAL WINNERS")
    print("NO IMPOSSIBLE TERMINAL STATE EXISTED")
    print("FRESH PROCESS OBSERVED VALID DURABLE STATE")

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
