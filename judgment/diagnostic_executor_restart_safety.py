from pathlib import Path
import json
import subprocess
import sys

from judgment.executor import execute_plan
from judgment.lifecycle import retry_failed_action
from state.state_reader import get_action_state

print("=== EXECUTOR RESTART SAFETY TEST ===")

action = get_action_state("free-disk-space")
assert action is not None, "free-disk-space action not found"

# Establish a terminal executed state.
action["status"] = "failed"
action["execution_result"] = "simulated-execution-failure"

retry = retry_failed_action(action)
assert retry["status"] == "approved"

result = execute_plan(
    [action],
    dry_run=True,
)

print("INITIAL EXECUTION:")
print(result)

persisted = get_action_state("free-disk-space")

print()
print("PERSISTED BEFORE RESTART:")
print(
    persisted.get("action"),
    "|",
    persisted.get("status"),
    "|",
    persisted.get("execution_result"),
)

assert persisted.get("status") == "executed"

child_code = r'''
from judgment.executor import execute_plan
from state.state_reader import get_action_state

action = get_action_state("free-disk-space")

print("CHILD PROCESS STATE:")
print(action)

result = execute_plan(
    [action],
    dry_run=True,
)

print("CHILD EXECUTOR ATTEMPT:")
print(result)

persisted = get_action_state("free-disk-space")

print("CHILD PERSISTED STATE:")
print(persisted)

assert any(
    item.get("status") == "blocked"
    and item.get("result") == "already-executed"
    for item in result
), "Fresh executor process did not block executed action."

assert persisted.get("status") == "executed", (
    "Executed state changed after restart."
)
'''

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print()
print(child.stdout)

if child.returncode != 0:
    print(child.stderr)
    raise SystemExit(child.returncode)

print("RESULT: PASS")
print("Persisted executed state survives executor restart.")
print("Fresh executor processes cannot duplicate execution.")
print("Executor and lifecycle boundaries remain consistent.")
