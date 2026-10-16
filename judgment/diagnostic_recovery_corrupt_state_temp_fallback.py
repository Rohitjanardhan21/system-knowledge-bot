from pathlib import Path
import json
import shutil
import uuid

from judgment.recovery import recover_interrupted_actions
from judgment.audit import load_audit

STATE = Path("state/latest.json")
TMP = Path("state/latest.tmp")
AUDIT = Path("audit/audit.json")

def completion_events(action, generation):
    return [
        e for e in load_audit()
        if isinstance(e, dict)
        and e.get("event") == "execution-completed"
        and e.get("action") == action
        and e.get("execution_generation") == generation
    ]

def main():
    action = f"recovery-tmp-fallback-{uuid.uuid4().hex[:8]}"
    generation = 1

    print("=== CORRUPTED STATE + DURABLE TEMP RECOVERY TEST ===")

    Path("state").mkdir(parents=True, exist_ok=True)

    # Preserve existing files.
    state_backup = STATE.with_suffix(".backup-test")
    tmp_backup = TMP.with_suffix(".backup-test")

    if state_backup.exists():
        state_backup.unlink()
    if tmp_backup.exists():
        tmp_backup.unlink()

    if STATE.exists():
        shutil.copy2(STATE, state_backup)
    if TMP.exists():
        shutil.copy2(TMP, tmp_backup)

    try:
        print("\n1. PREPARING VALID DURABLE TEMP STATE:")

        valid_state = {
            "actions": [
                {
                    "action": action,
                    "priority": "high",
                    "execution_mode": "automatic",
                    "status": "executing",
                    "retry_count": 0,
                    "max_retries": 2,
                    "escalation_required": False,
                    "execution_result": None,
                    "execution_generation": generation,
                    "execution_started_at": "2026-10-05T07:00:00+00:00",
                }
            ]
        }

        TMP.write_text(
            json.dumps(valid_state, indent=2),
            encoding="utf-8",
        )

        print(f"{action} | temp state exists | generation={generation}")
        assert TMP.exists()
        print("PASS")

        print("\n2. CORRUPTING AUTHORITATIVE STATE:")

        STATE.write_text(
            '{"actions": [CORRUPTED',
            encoding="utf-8",
        )

        print("latest.json contains invalid JSON.")
        print("PASS")

        print("\n3. FRESH-PROCESS RECOVERY:")

        result = recover_interrupted_actions()

        print("RECOVERY RESULT:", result)

        assert action in result
        print("Durable temp state was promoted and recovered.")
        print("PASS")

        print("\n4. VERIFYING RECOVERED STATE:")

        recovered = json.loads(STATE.read_text(encoding="utf-8"))
        item = next(
            a for a in recovered["actions"]
            if a["action"] == action
        )

        print(
            f"{action} | status={item['status']} | "
            f"result={item['execution_result']} | "
            f"generation={item['execution_generation']}"
        )

        assert item["status"] == "failed"
        assert item["execution_result"] == "interrupted-by-restart"
        assert item["execution_generation"] == generation

        print("Recovered state is correct.")
        print("PASS")

        print("\n5. VERIFYING TEMP FILE WAS CONSUMED:")

        print("latest.tmp exists:", TMP.exists())
        assert not TMP.exists()

        print("No orphaned temp state remains.")
        print("PASS")

        print("\n6. VERIFYING RECOVERY AUDIT:")

        audit = [
            e for e in load_audit()
            if isinstance(e, dict)
            and e.get("event") == "recovery-interrupted"
            and e.get("action") == action
        ]

        print("Recovery events:", len(audit))

        assert len(audit) == 1
        print("Exactly one recovery audit exists.")
        print("PASS")

        print("\n7. SECOND RECOVERY / IDEMPOTENCY:")

        second = recover_interrupted_actions()

        print("SECOND RECOVERY RESULT:", second)

        assert action not in second

        audit_after = [
            e for e in load_audit()
            if isinstance(e, dict)
            and e.get("event") == "recovery-interrupted"
            and e.get("action") == action
        ]

        assert len(audit_after) == 1

        print("Second recovery created no duplicate.")
        print("PASS")

        print("\n8. FRESH-PROCESS CONSISTENCY:")

        final_state = json.loads(
            STATE.read_text(encoding="utf-8")
        )

        final_item = next(
            a for a in final_state["actions"]
            if a["action"] == action
        )

        print(
            f"{action} | status={final_item['status']} | "
            f"generation={final_item['execution_generation']} | "
            f"result={final_item['execution_result']}"
        )

        assert final_item["status"] == "failed"
        assert final_item["execution_generation"] == generation

        print("Fresh state is consistent.")
        print("PASS")

        print("\n9. FINAL HARD INVARIANTS:")
        print("AUTHORITATIVE STATE WAS CORRUPTED")
        print("VALID DURABLE TEMP STATE EXISTED")
        print("RECOVERY PROMOTED THE TEMP STATE")
        print("STALE EXECUTION WAS RECOVERED")
        print("EXECUTION GENERATION REMAINED STABLE")
        print("TEMP FILE WAS REMOVED")
        print("EXACTLY ONE RECOVERY AUDIT EXISTS")
        print("SECOND RECOVERY WAS IDEMPOTENT")
        print("FRESH STATE REMAINED CONSISTENT")

        print("\nRESULT: PASS")

    finally:
        # Remove test artifacts and restore pre-test state.
        try:
            if STATE.exists():
                STATE.unlink()
            if state_backup.exists():
                shutil.move(state_backup, STATE)
        except Exception:
            pass

        try:
            if TMP.exists():
                TMP.unlink()
            if tmp_backup.exists():
                shutil.move(tmp_backup, TMP)
        except Exception:
            pass

if __name__ == "__main__":
    main()
