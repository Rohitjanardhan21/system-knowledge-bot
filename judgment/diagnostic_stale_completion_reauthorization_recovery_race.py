import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.audit import load_audit
from judgment.lifecycle import begin_execution, complete_execution
import judgment.recovery as recovery

STATE_PATH = Path("state/latest.json")
ACTION = f"stale-completion-reauthorization-race-{os.getpid()}"


def load_state():
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def get_action():
    return next(
        a for a in load_state()["actions"]
        if a.get("action") == ACTION
    )


def prepare_state():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = load_state() if STATE_PATH.exists() else {"actions": []}
    actions = state.setdefault("actions", [])
    target = next(
        (
            a for a in actions
            if isinstance(a, dict) and a.get("action") == ACTION
        ),
        None,
    )

    if target is None:
        target = {
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
            "execution_generation": 0,
        }
        actions.append(target)

    target["status"] = "approved"
    target["retry_count"] = 0
    target["max_retries"] = 2
    target["escalation_required"] = False
    target["execution_result"] = None

    for key in (
        "execution_started_at",
        "execution_completed_at",
        "recovery_reason",
    ):
        target.pop(key, None)

    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def completion_worker(action_name, generation, result, output):
    value = complete_execution(
        action_name,
        success=True,
        result=result,
        execution_generation=generation,
    )

    Path(output).write_text(
        json.dumps(value, indent=2),
        encoding="utf-8",
    )


def recovery_worker(output):
    value = recovery.recover_interrupted_actions()

    Path(output).write_text(
        json.dumps(value, indent=2),
        encoding="utf-8",
    )


def completion_events(generation=None):
    audit = load_audit()

    return [
        event
        for event in audit
        if event.get("event") == "execution-completed"
        and event.get("action") == ACTION
        and (
            generation is None
            or event.get("execution_generation") == generation
        )
    ]


def main():
    print("=== STALE COMPLETION + RECOVERY GENERATION FENCE TEST ===")

    print("\n1. PREPARING CLEAN APPROVED STATE:")
    prepare_state()

    target = get_action()
    print(
        ACTION,
        "| status =", target["status"],
        "| retry_count =", target.get("retry_count"),
    )

    assert target["status"] == "approved"
    print("PASS")

    print("\n2. STARTING GENERATION A:")
    start_a = begin_execution(ACTION)

    print("WORKER A:", start_a)

    assert start_a["status"] == "executing"
    generation_a = start_a["execution_generation"]

    print("Generation A:", generation_a)
    print("PASS")

    print("\n3. MAKING GENERATION A RECOVERY-ELIGIBLE:")

    state = load_state()
    target = next(
        a for a in state["actions"]
        if a.get("action") == ACTION
    )

    target["execution_started_at"] = "2000-01-01T00:00:00+00:00"

    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    print("Generation A marked stale.")
    print("PASS")

    print("\n4. RECOVERING GENERATION A:")
    recovery_result = recovery.recover_interrupted_actions()

    print("RECOVERY:", recovery_result)

    target = get_action()

    assert target["status"] in ("failed", "executed")
    print(
        ACTION,
        "| status =", target["status"],
        "| generation =", target.get("execution_generation"),
    )
    print("PASS")

    print("\n5. EXPLICITLY PREPARING NEW AUTHORIZATION STATE:")

    state = load_state()
    target = next(
        a for a in state["actions"]
        if a.get("action") == ACTION
    )

    target["status"] = "approved"
    target["execution_result"] = None
    target["retry_count"] = 0
    target["escalation_required"] = False

    for key in (
        "execution_started_at",
        "execution_completed_at",
        "recovery_reason",
    ):
        target.pop(key, None)

    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    print(
        ACTION,
        "| status =", get_action()["status"],
    )
    print("PASS")

    print("\n6. STARTING GENERATION B:")
    start_b = begin_execution(ACTION)

    print("WORKER B:", start_b)

    assert start_b["status"] == "executing"
    generation_b = start_b["execution_generation"]

    assert generation_b != generation_a

    print(
        "Generation A:", generation_a,
        "| Generation B:", generation_b,
    )
    print("NEW GENERATION CONFIRMED")
    print("PASS")

    print("\n7. STALE GENERATION A ATTEMPTS COMPLETION:")

    stale_output = Path("state") / "stale_generation_result.json"

    if stale_output.exists():
        stale_output.unlink()

    stale = multiprocessing.Process(
        target=completion_worker,
        args=(
            ACTION,
            generation_a,
            "STALE-GENERATION-A-MUST-NOT-WIN",
            str(stale_output),
        ),
    )

    stale.start()
    stale.join()

    assert stale.exitcode == 0

    stale_result = json.loads(
        stale_output.read_text(encoding="utf-8")
    )

    print("STALE RESULT:", stale_result)

    assert stale_result.get("status") == "blocked"

    print("STALE GENERATION WAS FENCED.")
    print("PASS")

    print("\n8. CURRENT GENERATION B COMPLETION RACE:")

    outputs = []

    for worker_id in range(1, 9):
        output = Path("state") / (
            f"current_generation_worker_{worker_id}.json"
        )

        if output.exists():
            output.unlink()

        process = multiprocessing.Process(
            target=completion_worker,
            args=(
                ACTION,
                generation_b,
                f"CURRENT-GENERATION-B-WORKER-{worker_id}",
                str(output),
            ),
        )

        process.start()
        outputs.append((process, output))

    for process, output in outputs:
        process.join()

    results = []

    for process, output in outputs:
        assert process.exitcode == 0

        results.append(
            json.loads(output.read_text(encoding="utf-8"))
        )

    for index, result in enumerate(results, 1):
        print(f"WORKER {index}:", result)

    successful = [
        result
        for result in results
        if result.get("status") == "executed"
    ]

    blocked = [
        result
        for result in results
        if result.get("status") == "blocked"
    ]

    print("\nSUCCESSFUL:", len(successful))
    print("BLOCKED:", len(blocked))

    assert len(successful) == 1
    assert len(blocked) == 7

    print("EXACTLY ONE CURRENT-GENERATION COMPLETION WON.")
    print("PASS")

    print("\n9. FINAL DURABLE STATE:")

    final_state = get_action()

    print(
        ACTION,
        "| status =", final_state["status"],
        "| result =", final_state.get("execution_result"),
        "| generation =", final_state.get("execution_generation"),
    )

    assert final_state["status"] == "executed"
    assert final_state["execution_generation"] == generation_b

    print("GENERATION B REMAINED AUTHORITATIVE.")
    print("PASS")

    print("\n10. AUDIT VERIFICATION:")

    stale_events = completion_events(generation_a)
    current_events = completion_events(generation_b)

    print(
        "Generation A completion events:",
        len(stale_events),
    )

    print(
        "Generation B completion events:",
        len(current_events),
    )

    assert not any(
        event.get("result") ==
        "STALE-GENERATION-A-MUST-NOT-WIN"
        for event in stale_events
    )

    assert len(current_events) == 1

    assert current_events[0]["execution_generation"] == generation_b

    print("NO STALE COMPLETION WAS ACCEPTED.")
    print("EXACTLY ONE CURRENT-GENERATION AUDIT EXISTS.")
    print("PASS")

    print("\n11. FRESH-PROCESS CONSISTENCY:")

    fresh = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json;"
                "from pathlib import Path;"
                "print(json.loads("
                "Path('state/latest.json').read_text("
                "encoding='utf-8'))['actions'])"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    print(fresh.stdout.strip())

    assert str(generation_b) in fresh.stdout

    print("FRESH PROCESS OBSERVED GENERATION B.")
    print("PASS")

    print("\n12. FINAL HARD INVARIANTS:")
    print("STALE GENERATION A COULD NOT COMPLETE")
    print("RE-AUTHORIZATION CREATED GENERATION B")
    print("GENERATION B REMAINED AUTHORITATIVE")
    print("NO STALE SUCCESS WAS DURABLY ACCEPTED")
    print("EXACTLY ONE CURRENT COMPLETION WON")
    print("EXACTLY ONE CURRENT COMPLETION AUDIT EXISTS")
    print("FRESH PROCESS OBSERVED THE SAME DURABLE GENERATION")
    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
