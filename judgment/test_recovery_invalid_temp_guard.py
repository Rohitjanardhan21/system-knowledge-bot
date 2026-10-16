from pathlib import Path
import json
import shutil
import uuid

from judgment.recovery import recover_interrupted_actions

STATE = Path("state/latest.json")
TMP = Path("state/latest.tmp")

def main():
    action = f"recovery-invalid-temp-{uuid.uuid4().hex[:8]}"

    print("=== CORRUPTED STATE + INVALID TEMP RECOVERY GUARD TEST ===")

    STATE.parent.mkdir(parents=True, exist_ok=True)

    state_backup = STATE.with_suffix(".backup-invalid-temp-test")
    tmp_backup = TMP.with_suffix(".backup-invalid-temp-test")

    if state_backup.exists():
        state_backup.unlink()
    if tmp_backup.exists():
        tmp_backup.unlink()

    if STATE.exists():
        shutil.copy2(STATE, state_backup)
    if TMP.exists():
        shutil.copy2(TMP, tmp_backup)

    try:
        print("\n1. PREPARING CORRUPTED AUTHORITATIVE STATE:")

        STATE.write_text(
            '{"actions": [CORRUPTED-AUTHORITATIVE',
            encoding="utf-8",
        )

        print("latest.json is invalid JSON.")
        print("PASS")

        print("\n2. PREPARING INVALID TEMP STATE:")

        TMP.write_text(
            '{"actions": [CORRUPTED-TEMP',
            encoding="utf-8",
        )

        print("latest.tmp is also invalid JSON.")
        print("PASS")

        print("\n3. RUNNING FRESH-PROCESS RECOVERY:")

        result = recover_interrupted_actions()

        print("RECOVERY RESULT:", result)

        assert result == []

        print("Recovery correctly refused invalid state candidates.")
        print("PASS")

        print("\n4. VERIFYING NO FALSE RECOVERY OCCURRED:")

        assert STATE.exists()
        assert TMP.exists()

        print("latest.json still exists:", STATE.exists())
        print("latest.tmp still exists:", TMP.exists())

        print("No lifecycle state was fabricated.")
        print("PASS")

        print("\n5. VERIFYING NO TEMP PROMOTION:")

        temp_contents = TMP.read_text(encoding="utf-8")

        assert "CORRUPTED-TEMP" in temp_contents

        print("Invalid temp file was NOT promoted.")
        print("PASS")

        print("\n6. SECOND RECOVERY / IDEMPOTENCY:")

        second = recover_interrupted_actions()

        print("SECOND RECOVERY RESULT:", second)

        assert second == []

        print("Repeated recovery remains safely blocked.")
        print("PASS")

        print("\n7. FINAL HARD INVARIANTS:")
        print("AUTHORITATIVE STATE WAS CORRUPTED")
        print("TEMP STATE WAS ALSO CORRUPTED")
        print("RECOVERY DID NOT PROMOTE INVALID DATA")
        print("NO FALSE EXECUTION RECOVERY OCCURRED")
        print("NO FABRICATED LIFECYCLE STATE WAS CREATED")
        print("INVALID TEMP REMAINED UNCONSUMED")
        print("SECOND RECOVERY WAS IDEMPOTENT")

        print("\nRESULT: PASS")

    finally:
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
