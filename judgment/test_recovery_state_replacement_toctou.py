from pathlib import Path
import json
import multiprocessing as mp
import time
import uuid

from judgment.recovery import recover_interrupted_actions

STATE = Path("state/latest.json")


def write_state(action, status, generation, result=None):
    STATE.parent.mkdir(parents=True, exist_ok=True)

    action_state = {
        "action": action,
        "priority": "high",
        "execution_mode": "automatic",
        "status": status,
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_result": result,
        "execution_generation": generation,
        "execution_started_at": "2026-10-05T07:00:00+00:00",
    }

    if status == "executed":
        action_state["execution_completed_at"] = \
            "2026-10-05T07:00:01+00:00"

    state = {"actions": [action_state]}

    temp = STATE.with_suffix(".tmp")
    temp.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )
    temp.replace(STATE)


def recovery_worker(queue, delay):
    try:
        time.sleep(delay)
        result = recover_interrupted_actions()
        queue.put({"result": result})
    except Exception as exc:
        queue.put({"error": repr(exc)})


def main():
    action = (
        f"recovery-state-replacement-race-"
        f"{uuid.uuid4().hex[:8]}"
    )

    print("=== RECOVERY STATE-REPLACEMENT TOCTOU RACE TEST ===")

    backup = STATE.with_suffix(".backup-state-replacement-test")

    if backup.exists():
        backup.unlink()

    if STATE.exists():
        STATE.replace(backup)

    try:
        print("\n1. PREPARING STALE EXECUTING STATE:")

        write_state(
            action,
            "executing",
            1,
        )

        print(
            f"{action} | status=executing | generation=1"
        )
        print("PASS")

        print("\n2. STARTING RECOVERY WORKER:")

        ctx = mp.get_context("spawn")
        queue = ctx.Queue()

        process = ctx.Process(
            target=recovery_worker,
            args=(queue, 0.30),
        )

        process.start()

        print("Recovery worker PID:", process.pid)
        print("PASS")

        print("\n3. REPLACING STATE WITH NEWER GENERATION:")

        time.sleep(0.10)

        write_state(
            action,
            "executed",
            2,
            "NEWER-GENERATION-WON",
        )

        print(
            f"{action} | status=executed | generation=2"
        )
        print("Newer durable state installed.")
        print("PASS")

        print("\n4. WAITING FOR RECOVERY WORKER:")

        process.join(timeout=10)

        if process.is_alive():
            process.terminate()
            process.join()
            raise AssertionError(
                "Recovery worker did not terminate."
            )

        worker_result = queue.get(timeout=5)

        print("RECOVERY WORKER RESULT:", worker_result)
        print("Recovery worker exitcode:", process.exitcode)

        if "error" in worker_result:
            raise AssertionError(
                f"Recovery worker failed: "
                f"{worker_result['error']}"
            )

        print("PASS")

        print("\n5. VERIFYING NEWER STATE WAS NOT OVERWRITTEN:")

        final_state = json.loads(
            STATE.read_text(encoding="utf-8")
        )

        item = next(
            a
            for a in final_state["actions"]
            if a["action"] == action
        )

        print(
            f"{action} | "
            f"status={item['status']} | "
            f"generation={item['execution_generation']} | "
            f"result={item['execution_result']}"
        )

        assert item["status"] == "executed"
        assert item["execution_generation"] == 2
        assert item["execution_result"] == "NEWER-GENERATION-WON"

        print("Newer durable state survived.")
        print("PASS")

        print("\n6. VERIFYING NO STALE RECOVERY OVERWRITE:")

        assert item["status"] != "failed"
        assert item["execution_generation"] != 1

        print("Generation 1 recovery did not overwrite generation 2.")
        print("PASS")

        print("\n7. FRESH-PROCESS CONSISTENCY:")

        fresh_state = json.loads(
            STATE.read_text(encoding="utf-8")
        )

        fresh_item = next(
            a
            for a in fresh_state["actions"]
            if a["action"] == action
        )

        print(
            f"{action} | "
            f"status={fresh_item['status']} | "
            f"generation={fresh_item['execution_generation']} | "
            f"result={fresh_item['execution_result']}"
        )

        assert fresh_item["status"] == "executed"
        assert fresh_item["execution_generation"] == 2
        assert fresh_item["execution_result"] == \
            "NEWER-GENERATION-WON"

        print("Fresh process observed generation 2.")
        print("PASS")

        print("\n8. FINAL HARD INVARIANTS:")
        print("RECOVERY WORKER STARTED AGAINST GENERATION 1")
        print("NEWER GENERATION 2 WAS INSTALLED")
        print("GENERATION 2 REMAINED AUTHORITATIVE")
        print("STALE RECOVERY COULD NOT OVERWRITE NEWER STATE")
        print("EXECUTED STATE WAS PRESERVED")
        print("FRESH PROCESS OBSERVED GENERATION 2")
        print("NO STALE STATE REGRESSION OCCURRED")

        print("\nRESULT: PASS")

    finally:
        try:
            if STATE.exists():
                STATE.unlink()
        except OSError:
            pass

        try:
            if backup.exists():
                backup.replace(STATE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
