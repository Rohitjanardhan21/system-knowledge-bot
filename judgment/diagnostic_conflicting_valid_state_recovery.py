import json
import subprocess
import sys
from pathlib import Path

from judgment.recovery import STATE_PATH

print("=== CONFLICTING VALID STATES RECOVERY SAFETY TEST ===")

TEMP_PATH = STATE_PATH.with_suffix(".tmp")
BACKUP_PATH = STATE_PATH.with_suffix(".conflict-backup")

original = STATE_PATH.read_bytes()
BACKUP_PATH.write_bytes(original)

state = json.loads(original)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Authoritative state: interrupted execution.
target["status"] = "executing"
target["execution_result"] = None

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. AUTHORITATIVE STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)
print("PASS")

# Create a VALID but conflicting temporary state.
temp_state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

temp_target = next(
    a for a in temp_state["actions"]
    if a.get("action") == "free-disk-space"
)

temp_target["status"] = "executed"
temp_target["execution_result"] = "conflicting-temp-success"

TEMP_PATH.write_text(
    json.dumps(temp_state, indent=2),
    encoding="utf-8",
)

print()
print("2. CONFLICTING VALID TEMP:")
print(
    temp_target["action"],
    "|",
    temp_target["status"],
    "|",
    temp_target.get("execution_result"),
)
print("PASS")

print()
print("3. FRESH PROCESS RECOVERY:")

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

print()
print("4. RESULTING STATE:")

try:
    resulting = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    result_target = next(
        a for a in resulting["actions"]
        if a.get("action") == "free-disk-space"
    )

    print(
        result_target["action"],
        "|",
        result_target.get("status"),
        "|",
        result_target.get("execution_result"),
    )

    if (
        result_target.get("status") == "executed"
        and result_target.get("execution_result")
        == "conflicting-temp-success"
    ):
        print(
            "WARNING: conflicting temporary state "
            "was promoted."
        )
    else:
        print(
            "Conflicting temporary success "
            "was not adopted."
        )

except Exception as exc:
    print(
        "STATE RESULT:",
        type(exc).__name__,
        "|",
        exc,
    )

print()
print("5. CLEANUP:")

STATE_PATH.write_bytes(original)

try:
    TEMP_PATH.unlink()
except OSError:
    pass

try:
    BACKUP_PATH.unlink()
except OSError:
    pass

print("authoritative state restored")
print("temporary state removed")
print("PASS")

print()
print("RESULT: TEST COMPLETE")
print("This establishes the conflicting-valid-state boundary.")
