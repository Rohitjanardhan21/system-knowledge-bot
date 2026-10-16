from pathlib import Path
import json
import subprocess
import sys

ROOT = Path.cwd()
STATE_PATH = ROOT / "state" / "latest.json"

print("=== RESTART-SAFE LIFECYCLE TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    (
        action
        for action in state.get("actions", [])
        if action.get("action") == "free-disk-space"
    ),
    None,
)

assert target is not None, "free-disk-space action not found"

# Establish an isolated known-good persisted state for this test.
target["status"] = "executed"
target["execution_result"] = "disk-cleanup-simulated"
target.pop("recovery_reason", None)
STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

print("PERSISTED BEFORE RESTART:")
print(
    target.get("action"),
    "|",
    target.get("status"),
    "|",
    target.get("execution_result"),
)

assert target.get("status") == "executed"

child_code = """
from state.state_reader import get_action_state
from judgment.lifecycle import begin_execution

action = get_action_state("free-disk-space")

print("CHILD PROCESS STATE:")
print(action)

result = begin_execution(action)

print("CHILD PROCESS RETRY:")
print(result)

assert result["status"] == "blocked"
assert "already been executed" in result["reason"]
"""

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=ROOT,
    capture_output=True,
    text=True,
)

print(child.stdout)

if child.returncode != 0:
    print(child.stderr)
    raise SystemExit(child.returncode)

print("RESULT: PASS")
print("Persisted executed state survives process restart.")
print("Executed actions remain non-executable in a fresh process.")
