from __future__ import annotations

import json
import multiprocessing as mp
import os
import queue
import subprocess
import sys
import time
import uuid
from pathlib import Path

from judgment.audit import load_audit, record_execution
from judgment.recovery import recover_interrupted_actions

STATE_PATH = Path("state") / "latest.json"
AUDIT_PATH = Path("state") / "audit.json"


def atomic_replace_state(state):
    """
    Deliberately bypass judgment.state_lock.

    This simulates an external/new-generation atomic replacement occurring
    after a stale recovery worker has already read Generation 1 but before
    that worker performs its final state replace.
    """
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    temp = STATE_PATH.with_name(
        f"{STATE_PATH.name}.{os.getpid()}.{uuid.uuid4().hex}.replacement.tmp"
    )

    with temp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp, STATE_PATH)


def read_state():
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def completion_events(action_name, generation):
    return [
        entry
        for entry in load_audit()
        if isinstance(entry, dict)
        and entry.get("event") == "execution-completed"
        and entry.get("action") == action_name
        and entry.get("execution_generation") == generation
    ]


def stale_recovery_worker(ready_queue, release_queue, result_queue):
    """
    Force recover_interrupted_actions() to pause at the exact dangerous point:

        Gen 1 has already been read and modified
        but _atomic_write_state() has not yet replaced latest.json.

    The parent installs Gen 2 during this pause.
    """
    import judgment.recovery as recovery

    original_atomic_write = recovery._atomic_write_state
    pause_used = False

    def intercepted_atomic_write(state, expected_state_bytes=None):
        nonlocal pause_used

        if not pause_used:
            pause_used = True

            actions = state.get("actions", [])
            snapshot = []

            for action in actions:
                if isinstance(action, dict):
                    snapshot.append(
                        {
                            "action": action.get("action"),
                            "status": action.get("status"),
                            "generation": action.get("execution_generation"),
                            "result": action.get("execution_result"),
                        }
                    )

            ready_queue.put(
                {
                    "event": "STALE-WRITE-READY",
                    "pid": os.getpid(),
                    "snapshot": snapshot,
                }
            )

            try:
                release_queue.get(timeout=20)
            except queue.Empty:
                result_queue.put(
                    {
                        "ok": False,
                        "error": "Timed out waiting for parent release.",
                    }
                )
                return

        return original_atomic_write(state, expected_state_bytes)

    recovery._atomic_write_state = intercepted_atomic_write

    try:
        result = recovery.recover_interrupted_actions()
        result_queue.put(
            {
                "ok": True,
                "result": result,
            }
        )
    except BaseException as exc:
        result_queue.put(
            {
                "ok": False,
                "error": repr(exc),
            }
        )


def normal_recovery_worker(result_queue):
    try:
        result_queue.put(recover_interrupted_actions())
    except BaseException as exc:
        result_queue.put({"error": repr(exc)})


def fresh_process_snapshot(action_name):
    code = r'''
import json
from pathlib import Path
from judgment.audit import load_audit

action_name = %r
state_path = Path("state") / "latest.json"

with state_path.open("r", encoding="utf-8") as f:
    state = json.load(f)

action = next(
    (
        a for a in state.get("actions", [])
        if isinstance(a, dict) and a.get("action") == action_name
    ),
    None,
)

events = [
    e for e in load_audit()
    if isinstance(e, dict)
    and e.get("event") == "execution-completed"
    and e.get("action") == action_name
]

print(json.dumps({
    "action": action,
    "completion_events": events,
}))
''' % action_name

    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(completed.stdout.strip())


def restore_file(path, original_bytes):
    if original_bytes is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original_bytes)


def main():
    print()
    print("=== AUDIT-FIRST GENERATION REPLACEMENT + TOCTOU RECOVERY TEST ===")
    print()

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    original_state = STATE_PATH.read_bytes() if STATE_PATH.exists() else None
    original_audit = AUDIT_PATH.read_bytes() if AUDIT_PATH.exists() else None

    action_name = f"audit-first-generation-replacement-{uuid.uuid4().hex[:8]}"

    gen1 = {
        "action": action_name,
        "status": "executing",
        "execution_generation": 1,
        "execution_result": None,
    }

    gen2 = {
        "action": action_name,
        "status": "executed",
        "execution_generation": 2,
        "execution_result": "GENERATION-2-AUTHORITATIVE",
    }

    try:
        print("1. INSTALLING GENERATION 1 EXECUTING STATE:")

        atomic_replace_state(
            {
                "actions": [gen1],
            }
        )

        state = read_state()
        action = state["actions"][0]

        print(
            f"{action_name} | "
            f"status={action.get('status')} | "
            f"generation={action.get('execution_generation')}"
        )

        assert action["status"] == "executing"
        assert action["execution_generation"] == 1

        print("PASS")
        print()

        print("2. WRITING GENERATION 1 COMPLETION AUDIT FIRST:")

        record_execution(
            [
                {
                    "event": "execution-completed",
                    "action": action_name,
                    "status": "executed",
                    "result": "GENERATION-1-AUDIT-FIRST",
                    "execution_generation": 1,
                }
            ]
        )

        gen1_events = completion_events(action_name, 1)

        print("Generation 1 completion audits:", len(gen1_events))

        assert len(gen1_events) == 1

        state = read_state()
        assert state["actions"][0]["status"] == "executing"

        print("Audit-first mismatch established.")
        print("PASS")
        print()

        print("3. STARTING STALE GENERATION 1 RECOVERY:")

        ctx = mp.get_context("spawn")

        ready_queue = ctx.Queue()
        release_queue = ctx.Queue()
        stale_result_queue = ctx.Queue()

        stale_worker = ctx.Process(
            target=stale_recovery_worker,
            args=(
                ready_queue,
                release_queue,
                stale_result_queue,
            ),
        )

        stale_worker.start()

        try:
            ready = ready_queue.get(timeout=20)
        except queue.Empty:
            stale_worker.terminate()
            stale_worker.join(timeout=5)
            raise AssertionError(
                "Stale recovery never reached the pre-write synchronization point."
            )

        print("Stale recovery PID:", ready.get("pid"))
        print("Recovery reached final atomic-write boundary.")
        print("Stale worker snapshot:", ready.get("snapshot"))

        stale_snapshot = next(
            (
                a
                for a in ready.get("snapshot", [])
                if a.get("action") == action_name
            ),
            None,
        )

        assert stale_snapshot is not None
        assert stale_snapshot["generation"] == 1
        assert stale_snapshot["status"] == "executed"

        print(
            "Generation 1 is now stale in worker memory, "
            "but has NOT yet performed its final state replace."
        )
        print("PASS")
        print()

        print("4. INSTALLING GENERATION 2 WHILE STALE RECOVERY IS PAUSED:")

        atomic_replace_state(
            {
                "actions": [gen2],
            }
        )

        state = read_state()
        action = state["actions"][0]

        print(
            f"{action_name} | "
            f"status={action.get('status')} | "
            f"result={action.get('execution_result')} | "
            f"generation={action.get('execution_generation')}"
        )

        assert action["execution_generation"] == 2
        assert action["status"] == "executed"
        assert action["execution_result"] == "GENERATION-2-AUTHORITATIVE"

        print("Generation 2 is now the authoritative lifecycle state.")
        print("PASS")
        print()

        print("5. RELEASING STALE GENERATION 1 RECOVERY:")

        release_queue.put("CONTINUE")

        stale_worker.join(timeout=20)

        if stale_worker.is_alive():
            stale_worker.terminate()
            stale_worker.join(timeout=5)
            raise AssertionError("Stale recovery worker did not terminate.")

        print("Stale recovery exitcode:", stale_worker.exitcode)

        assert stale_worker.exitcode == 0

        try:
            stale_result = stale_result_queue.get(timeout=5)
        except queue.Empty:
            raise AssertionError("Stale recovery worker returned no result.")

        print("Stale recovery result:", stale_result)

        assert stale_result.get("ok") is True

        print("PASS")
        print()

        print("6. VERIFYING GENERATION FENCE AFTER STALE WRITE ATTEMPT:")

        state = read_state()

        action = next(
            (
                a
                for a in state.get("actions", [])
                if isinstance(a, dict)
                and a.get("action") == action_name
            ),
            None,
        )

        if action is None:
            raise AssertionError(
                "Action disappeared after stale recovery write."
            )

        print(
            f"{action_name} | "
            f"status={action.get('status')} | "
            f"result={action.get('execution_result')} | "
            f"generation={action.get('execution_generation')}"
        )

        if action.get("execution_generation") != 2:
            raise AssertionError(
                "\nREAL TOCTOU DEFECT DETECTED:\n"
                "A stale Generation 1 recovery overwrote the authoritative "
                "Generation 2 lifecycle state.\n"
                f"Observed state: {action}"
            )

        if action.get("status") != "executed":
            raise AssertionError(
                "Generation 2 survived numerically but its terminal state "
                "was corrupted by stale recovery."
            )

        if action.get("execution_result") != "GENERATION-2-AUTHORITATIVE":
            raise AssertionError(
                "Generation 2 result was corrupted by stale recovery."
            )

        print("GENERATION 2 REMAINED AUTHORITATIVE.")
        print("PASS")
        print()

        print("7. VERIFYING AUDIT GENERATION ISOLATION:")

        gen1_events = completion_events(action_name, 1)
        gen2_events = completion_events(action_name, 2)

        print("Generation 1 completion audits:", len(gen1_events))
        print("Generation 2 completion audits:", len(gen2_events))

        assert len(gen1_events) == 1

        if len(gen2_events) != 0:
            raise AssertionError(
                "Stale Generation 1 recovery fabricated a Generation 2 "
                "completion audit."
            )

        print("Gen1 audit remained Gen1-specific.")
        print("No Gen2 completion audit was fabricated.")
        print("PASS")
        print()

        print("8. RUNNING CONCURRENT RECOVERY WAVE:")

        result_queue = ctx.Queue()
        workers = [
            ctx.Process(
                target=normal_recovery_worker,
                args=(result_queue,),
            )
            for _ in range(8)
        ]

        for worker in workers:
            worker.start()

        for worker in workers:
            worker.join(timeout=20)

        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
                raise AssertionError(
                    "Concurrent recovery worker did not terminate."
                )

        results = []

        for _ in workers:
            try:
                results.append(result_queue.get(timeout=5))
            except queue.Empty:
                results.append("<NO RESULT>")

        for i, result in enumerate(results, start=1):
            print(f"worker {i}: {result}")

        state = read_state()
        action = state["actions"][0]

        assert action["execution_generation"] == 2
        assert action["status"] == "executed"
        assert action["execution_result"] == "GENERATION-2-AUTHORITATIVE"

        print("Concurrent recovery did not corrupt Generation 2.")
        print("PASS")
        print()

        print("9. RECONCILING CURRENT GENERATION 2 EXACTLY ONCE:")

# The step 8 recovery wave already reconciled the missing Gen2 audit
        # exactly once; further waves must not add another.

        before = len(completion_events(action_name, 2))

        print("Gen2 completion audits before reconciliation:", before)

        assert before == 1

        ctx2 = mp.get_context("spawn")
        result_queue2 = ctx2.Queue()

        workers2 = [
            ctx2.Process(
                target=normal_recovery_worker,
                args=(result_queue2,),
            )
            for _ in range(8)
        ]

        for worker in workers2:
            worker.start()

        for worker in workers2:
            worker.join(timeout=20)

        for worker in workers2:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
                raise AssertionError(
                    "Generation 2 reconciliation worker did not terminate."
                )

        reconciliation_results = []

        for _ in workers2:
            try:
                reconciliation_results.append(
                    result_queue2.get(timeout=5)
                )
            except queue.Empty:
                reconciliation_results.append("<NO RESULT>")

        for i, result in enumerate(
            reconciliation_results,
            start=1,
        ):
            print(f"reconcile worker {i}: {result}")

        after = len(completion_events(action_name, 2))

        print("Gen2 completion audits after reconciliation:", after)

        assert after == 1, (
            "Generation 2 must have exactly one completion audit."
        )

        print("GENERATION 2 RECONCILED EXACTLY ONCE.")
        print("PASS")
        print()

        print("10. VERIFYING SECOND RECOVERY WAVE IS IDEMPOTENT:")

        second_results = []

        for _ in range(4):
            second_results.append(recover_interrupted_actions())

        for i, result in enumerate(second_results, start=1):
            print(f"second-wave {i}: {result}")

        final_gen1_events = completion_events(action_name, 1)
        final_gen2_events = completion_events(action_name, 2)

        print("Final Gen1 completion audits:", len(final_gen1_events))
        print("Final Gen2 completion audits:", len(final_gen2_events))

        assert len(final_gen1_events) == 1
        assert len(final_gen2_events) == 1

        state = read_state()
        action = state["actions"][0]

        assert action["execution_generation"] == 2
        assert action["status"] == "executed"
        assert action["execution_result"] == "GENERATION-2-AUTHORITATIVE"

        print("No duplicate completion audits created.")
        print("PASS")
        print()

        print("11. VERIFYING CONSISTENCY FROM A FRESH PROCESS:")

        snapshot = fresh_process_snapshot(action_name)

        fresh_action = snapshot["action"]
        fresh_events = snapshot["completion_events"]

        print("Fresh-process state:", fresh_action)
        print(
            "Fresh-process completion generations:",
            [
                event.get("execution_generation")
                for event in fresh_events
            ],
        )

        assert fresh_action is not None
        assert fresh_action["execution_generation"] == 2
        assert fresh_action["status"] == "executed"
        assert (
            fresh_action["execution_result"]
            == "GENERATION-2-AUTHORITATIVE"
        )

        gen1_count = sum(
            event.get("execution_generation") == 1
            for event in fresh_events
        )

        gen2_count = sum(
            event.get("execution_generation") == 2
            for event in fresh_events
        )

        assert gen1_count == 1
        assert gen2_count == 1

        print("Fresh process sees the same authoritative state.")
        print("PASS")
        print()

        print("12. RESULT:")
        print(
            "PASS - audit-first recovery remained generation-fenced "
            "across the forced TOCTOU replacement window."
        )

    finally:
        print()
        print("Restoring pre-test state and audit files...")

        restore_file(STATE_PATH, original_state)
        restore_file(AUDIT_PATH, original_audit)

        # Remove common temporary artifacts belonging to recovery/audit.
        for path in [
            STATE_PATH.with_suffix(".tmp"),
            AUDIT_PATH.with_suffix(".tmp"),
        ]:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

        # Remove replacement temp files if a failed run left any behind.
        for path in STATE_PATH.parent.glob(
            f"{STATE_PATH.name}.*.replacement.tmp"
        ):
            try:
                path.unlink()
            except OSError:
                pass

        print("Original files restored.")


if __name__ == "__main__":
    mp.freeze_support()
    main()
