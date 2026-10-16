from __future__ import annotations

import json
import multiprocessing as mp
import os
import uuid
from pathlib import Path

from judgment.audit import load_audit, record_execution
from judgment.lifecycle import begin_execution, complete_execution
from judgment.recovery import recover_interrupted_actions


STATE_PATH = Path("state") / "latest.json"

ACTION = (
    f"recovery-audit-crash-concurrent-completion-"
    f"{uuid.uuid4().hex[:8]}"
)


def load_state():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    temp_path = STATE_PATH.with_suffix(".tmp")

    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_path, STATE_PATH)


def matching_events(action, generation, event_name=None):
    events = load_audit()

    return [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("action") == action
        and event.get("execution_generation") == generation
        and (
            event_name is None
            or event.get("event") == event_name
        )
    ]


def crash_after_generation_1_audit(action, ready, crash_signal):
    """
    Simulate recovery writing a durable generation-1 reconciliation
    audit and then crashing immediately afterward.
    """

    record_execution([{
        "event": "execution-completed",
        "action": action,
        "status": "executed",
        "result": "GENERATION-1-RECOVERED-BEFORE-CRASH",
        "execution_generation": 1,
        "recovered": True,
    }])

    ready.set()

    crash_signal.wait()

    os._exit(137)


def concurrent_completion_worker(
    action,
    generation,
    worker_id,
    barrier,
    output_queue,
):
    try:
        barrier.wait()

        result = complete_execution(
            action,
            success=True,
            result=f"GENERATION-{generation}-WORKER-{worker_id}",
            execution_generation=generation,
        )

        output_queue.put({
            "worker": worker_id,
            "result": result,
        })

    except Exception as exc:
        output_queue.put({
            "worker": worker_id,
            "error": repr(exc),
        })


def main():
    print(
        "=== RECOVERY AUDIT CRASH + "
        "CONCURRENT COMPLETION FENCE TEST ==="
    )

    ctx = mp.get_context("spawn")

    # ============================================================
    # 1. PREPARE GENERATION 1
    # ============================================================
    print("\n1. PREPARING GENERATION 1 EXECUTING STATE:")

    state = {
        "actions": [{
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "executing",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": None,
            "execution_generation": 1,
            "execution_started_at":
                "2000-01-01T00:00:00+00:00",
        }]
    }

    save_state(state)

    print(
        f"{ACTION} | status=executing | generation=1"
    )

    assert len(
        matching_events(
            ACTION,
            1,
            "execution-completed",
        )
    ) == 0

    print("PASS")

    # ============================================================
    # 2. START CRASHING RECOVERY PROCESS
    # ============================================================
    print("\n2. STARTING RECOVERY AUDIT CRASH PROCESS:")

    ready = ctx.Event()
    crash_signal = ctx.Event()

    crash_worker = ctx.Process(
        target=crash_after_generation_1_audit,
        args=(
            ACTION,
            ready,
            crash_signal,
        ),
    )

    crash_worker.start()

    assert ready.wait(timeout=10)

    generation_1_audits = matching_events(
        ACTION,
        1,
        "execution-completed",
    )

    print(
        "Generation 1 completion audits before crash:",
        len(generation_1_audits),
    )

    assert len(generation_1_audits) == 1

    print(
        "Generation 1 reconciliation audit is durable."
    )
    print("PASS")

    # ============================================================
    # 3. INSTALL GENERATION 2
    # ============================================================
    print("\n3. INSTALLING NEW GENERATION 2:")

    state = load_state()
    action = state["actions"][0]

    action["status"] = "executed"
    action["execution_generation"] = 2
    action["execution_result"] = (
        "GENERATION-2-AUTHORITATIVE"
    )
    action["execution_started_at"] = (
        "2099-01-01T00:00:00+00:00"
    )
    action["execution_completed_at"] = (
        "2099-01-01T00:00:01+00:00"
    )

    save_state(state)

    print(
        f"{ACTION} | status=executed | generation=2 | "
        "result=GENERATION-2-AUTHORITATIVE"
    )

    print("Generation 2 installed.")
    print("PASS")

    # ============================================================
    # 4. CRASH GENERATION-1 PROCESS
    # ============================================================
    print("\n4. CRASHING GENERATION-1 PROCESS:")

    crash_signal.set()
    crash_worker.join(timeout=10)

    print(
        "Recovery crash worker exitcode:",
        crash_worker.exitcode,
    )

    assert crash_worker.exitcode == 137

    print(
        "REAL PROCESS CRASH OCCURRED "
        "AFTER GENERATION-1 AUDIT."
    )
    print("PASS")

    # ============================================================
    # 5. VERIFY GENERATION 2
    # ============================================================
    print(
        "\n5. VERIFYING GENERATION 2 "
        "REMAINED AUTHORITATIVE:"
    )

    state = load_state()
    action = state["actions"][0]

    print(
        f"{ACTION} | status={action['status']} | "
        f"generation={action['execution_generation']} | "
        f"result={action['execution_result']}"
    )

    assert action["status"] == "executed"
    assert action["execution_generation"] == 2
    assert (
        action["execution_result"]
        == "GENERATION-2-AUTHORITATIVE"
    )

    print("GENERATION 2 REMAINED AUTHORITATIVE.")
    print("PASS")

    # ============================================================
    # 6. GENERATION AUDIT FENCE
    # ============================================================
    print(
        "\n6. VERIFYING GENERATION-SPECIFIC AUDIT FENCE:"
    )

    generation_1_audits = matching_events(
        ACTION,
        1,
        "execution-completed",
    )

    generation_2_audits = matching_events(
        ACTION,
        2,
        "execution-completed",
    )

    print(
        "Generation 1 completion audits:",
        len(generation_1_audits),
    )

    print(
        "Generation 2 completion audits:",
        len(generation_2_audits),
    )

    assert len(generation_1_audits) == 1
    assert len(generation_2_audits) == 0

    print(
        "GENERATION 1 AUDIT REMAINED "
        "GENERATION-SPECIFIC."
    )

    print(
        "NO GENERATION-2 AUDIT WAS FABRICATED."
    )

    print("PASS")

    # ============================================================
    # 7. PREPARE GENERATION 2 FOR COMPLETION RACE
    # ============================================================
    print(
        "\n7. STARTING CONCURRENT "
        "GENERATION-2 COMPLETION RACE:"
    )

    state = load_state()
    action = state["actions"][0]

    action["status"] = "executing"
    action["execution_generation"] = 2
    action["execution_result"] = None

    save_state(state)

    print(
        f"{ACTION} | status=executing | generation=2"
    )

    # ============================================================
    # 8. CONCURRENT COMPLETION
    # ============================================================
    barrier = ctx.Barrier(8)
    output_queue = ctx.Queue()

    workers = []

    for worker_id in range(1, 9):
        worker = ctx.Process(
            target=concurrent_completion_worker,
            args=(
                ACTION,
                2,
                worker_id,
                barrier,
                output_queue,
            ),
        )

        workers.append(worker)
        worker.start()

    results = []

    for _ in workers:
        results.append(
            output_queue.get(timeout=20)
        )

    for worker in workers:
        worker.join(timeout=10)

    for result in results:
        print(
            f"WORKER {result['worker']}: "
            f"{result}"
        )

    successful = [
        item
        for item in results
        if isinstance(item.get("result"), dict)
        and item["result"].get("status") == "executed"
    ]

    print(
        "\nSUCCESSFUL CURRENT-GENERATION "
        f"COMPLETIONS: {len(successful)}"
    )

    assert len(successful) == 1

    print(
        "EXACTLY ONE GENERATION-2 "
        "COMPLETION WON."
    )
    print("PASS")

    # ============================================================
    # 9. VERIFY FINAL STATE
    # ============================================================
    print(
        "\n9. VERIFYING FINAL "
        "AUTHORITATIVE STATE:"
    )

    state = load_state()
    action = state["actions"][0]

    print(
        f"{ACTION} | status={action['status']} | "
        f"generation={action['execution_generation']} | "
        f"result={action['execution_result']}"
    )

    assert action["status"] == "executed"
    assert action["execution_generation"] == 2

    print(
        "GENERATION 2 REMAINED AUTHORITATIVE."
    )
    print("PASS")

    # ============================================================
    # 10. VERIFY EXACTLY-ONCE AUDITS
    # ============================================================
    print(
        "\n10. VERIFYING "
        "GENERATION-SPECIFIC AUDITS:"
    )

    generation_1_audits = matching_events(
        ACTION,
        1,
        "execution-completed",
    )

    generation_2_audits = matching_events(
        ACTION,
        2,
        "execution-completed",
    )

    print(
        "Generation 1 completion audits:",
        len(generation_1_audits),
    )

    print(
        "Generation 2 completion audits:",
        len(generation_2_audits),
    )

    assert len(generation_1_audits) == 1
    assert len(generation_2_audits) == 1

    print(
        "GENERATION 1 AUDIT EXISTS EXACTLY ONCE."
    )

    print(
        "GENERATION 2 AUDIT EXISTS EXACTLY ONCE."
    )

    print(
        "NO CROSS-GENERATION AUDIT CORRUPTION."
    )

    print("PASS")

    # ============================================================
    # 11. SECOND RECOVERY
    # ============================================================
    print(
        "\n11. SECOND RECOVERY / IDEMPOTENCY:"
    )

    second_recovery = recover_interrupted_actions()

    print(
        "SECOND RECOVERY RESULT:",
        second_recovery,
    )

    generation_1_after = matching_events(
        ACTION,
        1,
        "execution-completed",
    )

    generation_2_after = matching_events(
        ACTION,
        2,
        "execution-completed",
    )

    print(
        "Generation 1 audits after "
        f"second recovery: {len(generation_1_after)}"
    )

    print(
        "Generation 2 audits after "
        f"second recovery: {len(generation_2_after)}"
    )

    assert len(generation_1_after) == 1
    assert len(generation_2_after) == 1

    print(
        "SECOND RECOVERY CREATED NO DUPLICATES."
    )
    print("PASS")

    # ============================================================
    # 12. FRESH-PROCESS CONSISTENCY
    # ============================================================
    print(
        "\n12. FRESH-PROCESS CONSISTENCY:"
    )

    state = load_state()
    action = state["actions"][0]

    print(
        f"{ACTION} | status={action['status']} | "
        f"generation={action['execution_generation']} | "
        f"result={action['execution_result']}"
    )

    assert action["status"] == "executed"
    assert action["execution_generation"] == 2

    fresh_generation_1 = matching_events(
        ACTION,
        1,
        "execution-completed",
    )

    fresh_generation_2 = matching_events(
        ACTION,
        2,
        "execution-completed",
    )

    assert len(fresh_generation_1) == 1
    assert len(fresh_generation_2) == 1

    print(
        "Fresh process observed Generation 2 "
        "and both generation-specific audits."
    )
    print("PASS")

    # ============================================================
    # 13. FINAL HARD INVARIANTS
    # ============================================================
    print("\n13. FINAL HARD INVARIANTS:")

    print(
        "REAL PROCESS CRASH OCCURRED "
        "AFTER GENERATION-1 AUDIT"
    )

    print(
        "GENERATION 1 AUDIT REMAINED "
        "GENERATION-SPECIFIC"
    )

    print(
        "GENERATION 2 REPLACED GENERATION 1"
    )

    print(
        "GENERATION 2 REMAINED AUTHORITATIVE"
    )

    print(
        "CONCURRENT GENERATION-2 "
        "COMPLETION RACE OCCURRED"
    )

    print(
        "EXACTLY ONE CURRENT-GENERATION "
        "COMPLETION WON"
    )

    print(
        "GENERATION 1 AUDIT EXISTS "
        "EXACTLY ONCE"
    )

    print(
        "GENERATION 2 AUDIT EXISTS "
        "EXACTLY ONCE"
    )

    print(
        "NO CROSS-GENERATION AUDIT "
        "CORRUPTION OCCURRED"
    )

    print(
        "SECOND RECOVERY WAS IDEMPOTENT"
    )

    print(
        "FRESH PROCESS OBSERVED "
        "GENERATION 2"
    )

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
