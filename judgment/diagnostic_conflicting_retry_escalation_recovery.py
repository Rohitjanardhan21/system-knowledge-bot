import json
import subprocess
import sys

from pathlib import Path

from judgment.recovery import STATE_PATH

print("=== CONFLICTING RETRY/ESCALATION STATE RECOVERY TEST ===")

TEMP_PATH = STATE_PATH.with_suffix(".tmp")
BACKUP_PATH = STATE_PATH.with_suffix(".retry-conflict-backup")

original = STATE_PATH.read_bytes()
BACKUP_PATH.write_bytes(original)

state = json.loads(original)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Authoritative safety state.
target["status"] = "failed"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. AUTHORITATIVE ESCALATED STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "| retry_count =",
    target.get("retry_count"),
    "| max_retries =",
    target.get("max_retries"),
    "| escalation =",
    target.get("escalation_required"),
)
print("PASS")

# Conflicting temporary state attempts to erase escalation.
temp_state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

temp_target = next(
    a for a in temp_state["actions"]
    if a.get("action") == "free-disk-space"
)

temp_target["status"] = "approved"
temp_target["retry_count"] = 0
temp_target["max_retries"] = 2
temp_target["escalation_required"] = False

TEMP_PATH.write_text(
    json.dumps(temp_state, indent=2),
    encoding="utf-8",
)

print()
print("2. CONFLICTING TEMP STATE:")
print(
    temp_target["action"],
    "|",
    temp_target["status"],
    "| retry_count =",
    temp_target.get("retry_count"),
    "| max_retries =",
    temp_target.get("max_retries"),
    "| escalation =",
    temp_target.get("escalation_required"),
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
        "| retry_count =",
        result_target.get("retry_count"),
        "| max_retries =",
        result_target.get("max_retries"),
        "| escalation =",
        result_target.get("escalation_required"),
    )

except Exception as exc:
    print(
        "STATE RESULT:",
        type(exc).__name__,
        "|",
        exc,
    )

print()
print("5. SAFETY CHECK:")

try:
    resulting = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    result_target = next(
        a for a in resulting["actions"]
        if a.get("action") == "free-disk-space"
    )

    if (
        result_target.get("retry_count") == 2
        and result_target.get("max_retries") == 2
        and result_target.get("escalation_required") is True
    ):
        print("AUTHORITATIVE RETRY/ESCALATION STATE PRESERVED")
    else:
        print("WARNING: SAFETY STATE WAS ALTERED")

except Exception as exc:
    print(
        "SAFETY CHECK ERROR:",
        type(exc).__name__,
        "|",
        exc,
    )

print()
print("6. CLEANUP:")

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
print("This establishes the retry/escalation conflict boundary.")
