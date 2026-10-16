from pathlib import Path
import json

if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.recovery import recover_interrupted_actions

STATE_PATH = Path("state/latest.json")
TEMP_PATH = STATE_PATH.with_suffix(".tmp")

print("=== ORPHANED TEMP CLEANUP TEST ===")

# Establish valid authoritative state.
state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "approved"
target.pop("execution_completed_at", None)
target.pop("execution_result", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

# Create an orphaned temporary file.
TEMP_PATH.write_text(
    json.dumps(
        {
            "actions": [
                {
                    "action": "free-disk-space",
                    "status": "executing",
                }
            ]
        },
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("1. INITIAL STATE:")
print(
    target["action"],
    "|",
    target["status"],
)

print(
    "TEMPORARY FILE EXISTS:",
    TEMP_PATH.exists(),
)

assert target["status"] == "approved"
assert TEMP_PATH.exists()

print()
print("2. RUNNING RECOVERY...")

recover_interrupted_actions()

print()
print("3. VERIFYING AUTHORITATIVE STATE:")

final_state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

final_target = next(
    a for a in final_state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    final_target["action"],
    "|",
    final_target["status"],
)

assert final_target["status"] == "approved"

print()
print("4. VERIFYING TEMPORARY FILE:")

print(
    "TEMPORARY FILE EXISTS:",
    TEMP_PATH.exists(),
)

if TEMP_PATH.exists():
    print("NOTE: Recovery currently preserves the orphaned temp file.")

print()
print("5. RESULT:")

if TEMP_PATH.exists():
    print("RESULT: BASELINE")
    print("Authoritative state is safe.")
    print("Orphaned temp file still requires cleanup implementation.")
else:
    print("RESULT: PASS")
    print("Orphaned temporary state was cleaned.")
    print("Authoritative state remained unchanged.")
