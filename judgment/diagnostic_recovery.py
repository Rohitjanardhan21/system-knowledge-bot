from pathlib import Path
import json
import subprocess
import sys

STATE_PATH = Path("state") / "latest.json"

print("=== CRASH/RESTART RECOVERY TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = None

for action in state.get("actions", []):
    if action.get("action") == "free-disk-space":
        target = action
        break

assert target is not None, "free-disk-space action not found"

original_status = target.get("status")

print("ORIGINAL:")
print(
    target.get("action"),
    "|",
    original_status,
    "|",
    target.get("execution_result"),
)

# Simulate a process crash while execution was in progress.
target["status"] = "executing"
target.pop("execution_completed_at", None)
target.pop("execution_result", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("SIMULATED CRASH STATE:")
print(target.get("action"), "|", target.get("status"))

# Recovery happens in a fresh Python process.
child_code = """
from judgment.recovery import recover_interrupted_actions

recovered = recover_interrupted_actions()

print("RECOVERED ACTIONS:")
print(recovered)

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

# Reload state after recovery.
state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    action
    for action in state.get("actions", [])
    if action.get("action") == "free-disk-space"
)

print("AFTER RECOVERY:")
print(
    target.get("action"),
    "|",
    target.get("status"),
    "|",
    target.get("execution_result"),
)

assert target.get("status") == "failed"
assert target.get("execution_result") == "interrupted-by-restart"

print()
print("RESULT: PASS")
print("Interrupted execution is detected after restart.")
print("Executing actions are not silently treated as successful.")
print("Recovery persists the interrupted state.")
