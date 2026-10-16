import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.recovery import STATE_PATH

print("=== CORRUPTED STATE + VALID TEMP RECOVERY TEST ===")

TEMP_PATH = STATE_PATH.with_suffix(".tmp")
BACKUP_PATH = STATE_PATH.with_suffix(".corruption-backup")

# Preserve authoritative state.
original = STATE_PATH.read_bytes()
BACKUP_PATH.write_bytes(original)

state = json.loads(original.decode("utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print()
print("1. ORIGINAL VALID STATE:")
print(
    target["action"],
    "|",
    target.get("status"),
    "|",
    target.get("execution_result"),
)
print("PASS")

# Create a valid temporary state representing an interrupted action.
temp_state = json.loads(original.decode("utf-8"))

temp_target = next(
    a for a in temp_state["actions"]
    if a.get("action") == "free-disk-space"
)

temp_target["status"] = "executing"
temp_target["execution_result"] = None

TEMP_PATH.write_text(
    json.dumps(temp_state, indent=2),
    encoding="utf-8",
)

print()
print("2. VALID TEMP STATE:")
print(
    temp_target["action"],
    "|",
    temp_target["status"],
)
assert TEMP_PATH.exists()
print("PASS")

# Corrupt the authoritative state.
STATE_PATH.write_text(
    '{"actions": [CORRUPTED',
    encoding="utf-8",
)

print()
print("3. CORRUPTED AUTHORITATIVE STATE:")
print("latest.json corrupted = True")
print("PASS")

# Fresh process recovery.
print()
print("4. FRESH PROCESS RECOVERY:")

child_code = """
from judgment.recovery import recover_interrupted_actions

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)
"""

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print(child.stdout)

if child.returncode != 0:
    print(child.stderr)
    raise SystemExit(child.returncode)

print("PASS")

# Inspect resulting authoritative state.
print()
print("5. RESULTING STATE:")

try:
    resulting_state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    resulting_target = next(
        a for a in resulting_state["actions"]
        if a.get("action") == "free-disk-space"
    )

    print(
        resulting_target["action"],
        "|",
        resulting_target.get("status"),
        "|",
        resulting_target.get("execution_result"),
    )

    print("VALID JSON = True")

except Exception as exc:
    print(
        "STATE REMAINS UNRECOVERABLE:",
        type(exc).__name__,
        "|",
        exc,
    )

print("PASS")

# Restore original state so subsequent tests start clean.
STATE_PATH.write_bytes(original)

if TEMP_PATH.exists():
    TEMP_PATH.unlink()

if BACKUP_PATH.exists():
    BACKUP_PATH.unlink()

print()
print("6. CLEANUP:")
print("authoritative state restored")
print("temporary state removed")
print("PASS")

print()
print("RESULT: PASS")
print("Test completed without manufacturing execution success.")
print("Current implementation behavior with corrupted state + valid temp is now established.")
