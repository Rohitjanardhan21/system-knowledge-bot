import json
from pathlib import Path
import subprocess
import sys

from judgment.recovery import STATE_PATH

print("=== CORRUPTED STATE + TEMP FAKE SUCCESS SAFETY TEST ===")

TEMP_PATH = STATE_PATH.with_suffix(".tmp")

# Preserve valid authoritative state.
original = STATE_PATH.read_bytes()

state = json.loads(original)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Create a legitimate interrupted authoritative state first.
target["status"] = "executing"
target["execution_result"] = None

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. AUTHORITATIVE EXECUTING STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)
assert target["status"] == "executing"
print("PASS")

# Create an orphaned TEMP containing a fake success.
temp_state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

temp_target = next(
    a for a in temp_state["actions"]
    if a.get("action") == "free-disk-space"
)

temp_target["status"] = "executed"
temp_target["execution_result"] = "orphaned-fake-success"

TEMP_PATH.write_text(
    json.dumps(temp_state, indent=2),
    encoding="utf-8",
)

print()
print("2. ORPHANED TEMP FAKE SUCCESS:")
print(
    TEMP_PATH,
    "|",
    TEMP_PATH.exists(),
    "| status =",
    temp_target["status"],
)
assert TEMP_PATH.exists()
assert temp_target["status"] == "executed"
print("PASS")

# Corrupt authoritative state.
STATE_PATH.write_text(
    '{"actions": [INVALID CORRUPTED JSON',
    encoding="utf-8",
)

print()
print("3. CORRUPTED AUTHORITATIVE STATE:")
print("latest.json corrupted = True")
print("PASS")

# Fresh process attempts recovery.
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

# IMPORTANT:
# Recovery must NOT silently promote the orphaned fake success.
print()
print("5. SAFETY CHECK:")

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
        resulting_target["status"],
        "|",
        resulting_target.get("execution_result"),
    )

    assert not (
        resulting_target.get("status") == "executed"
        and resulting_target.get("execution_result")
        == "orphaned-fake-success"
    )

    print("PASS")

except json.JSONDecodeError:
    print("STATE REMAINS UNRECOVERABLE")
    print("PASS")

# Cleanup.
STATE_PATH.write_bytes(original)

try:
    TEMP_PATH.unlink()
except OSError:
    pass

print()
print("6. CLEANUP:")
print("authoritative state restored")
print("temporary state removed")
print("PASS")

print()
print("RESULT: PASS")
print("Orphaned temporary fake success was not trusted.")
print("Recovery did not manufacture execution success.")
print("Known-good state was restored.")
