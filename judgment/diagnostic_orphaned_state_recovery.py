import json
from pathlib import Path
import subprocess
import sys

from judgment.recovery import STATE_PATH

print("=== ORPHANED STATE TEMP → RESTART RECOVERY TEST ===")

TEMP_PATH = STATE_PATH.with_suffix(".tmp")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Establish authoritative interrupted state.
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

assert target["status"] == "executing"
print("PASS")

# Simulate an orphaned temporary state file containing a
# potentially misleading successful state.
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
print("2. ORPHANED TEMP FILE:")
print(
    TEMP_PATH,
    "| exists =",
    TEMP_PATH.exists(),
)

assert TEMP_PATH.exists()
print("PASS")

# Fresh process performs recovery.
print()
print("3. FRESH PROCESS RECOVERY:")

child_code = """
from judgment.recovery import recover_interrupted_actions

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

assert "free-disk-space" in recovered
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

# Verify authoritative state.
state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print()
print("4. FINAL AUTHORITATIVE STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)

assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"

print("PASS")

print()
print("5. TEMP FILE CLEANUP:")
print("exists =", TEMP_PATH.exists())

assert not TEMP_PATH.exists()

print("PASS")

print()
print("RESULT: PASS")
print("Orphaned temporary state was detected.")
print("Authoritative latest.json remained the source of truth.")
print("Interrupted execution became failed.")
print("Orphaned temporary state was cleaned after restart.")
