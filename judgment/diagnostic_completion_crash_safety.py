import json
from pathlib import Path
import subprocess
import sys

STATE_PATH = Path("state") / "latest.json"

print("=== EXECUTION COMPLETION CRASH SAFETY TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Start from an executing action.
target["status"] = "executing"
target["execution_result"] = None
target.pop("execution_completed_at", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. EXECUTING STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)

assert target["status"] == "executing"
print("PASS")

# Fresh process simulates restart before completion was durably committed.
print()
print("2. FRESH PROCESS RECOVERY:")

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

# Verify authoritative state.
state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print()
print("3. POST-CRASH STATE:")
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
print("RESULT: PASS")
print("An incomplete completion cannot become success.")
print("Restart converts ambiguous execution into failed.")
print("The completion boundary remains crash-safe.")
