import json
import subprocess
import sys
from pathlib import Path

from state.state_reader import get_action_state
from judgment.lifecycle import retry_failed_action
from judgment.recovery import recover_interrupted_actions

print("=== EXECUTOR CRASH RECOVERY TEST ===")

action = get_action_state("free-disk-space")
assert action is not None, "free-disk-space action not found"

# Establish a controlled approved state.
action["status"] = "failed"
action["execution_result"] = "simulated-previous-failure"

retry = retry_failed_action(action)
assert retry["status"] == "approved"

print("BEFORE CRASH:")
print(action["action"], "|", action["status"])

# Simulate the executor reaching the executing boundary,
# but crashing before completion.
child_code = r'''
from state.state_reader import get_action_state
from judgment.lifecycle import begin_execution

action = get_action_state("free-disk-space")

result = begin_execution(action)

print("CHILD START:")
print(result)

assert result["status"] == "executing"

# Simulated crash: deliberately do not call complete_execution().
raise SystemExit(99)
'''

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print()
print("CHILD PROCESS:")
print(child.stdout)

assert child.returncode == 99

persisted = get_action_state("free-disk-space")

print("PERSISTED AFTER CRASH:")
print(
    persisted.get("action"),
    "|",
    persisted.get("status"),
)

assert persisted.get("status") == "executing"

# Recovery must detect the interrupted execution.
recovered = recover_interrupted_actions()

print()
print("RECOVERED:")
print(recovered)

assert "free-disk-space" in recovered

final_state = get_action_state("free-disk-space")

print()
print("FINAL STATE:")
print(
    final_state.get("action"),
    "|",
    final_state.get("status"),
    "|",
    final_state.get("execution_result"),
)

assert final_state.get("status") == "failed"
assert final_state.get("execution_result") == "interrupted-by-restart"

# Recovery must not silently make the action successful.
assert final_state.get("status") != "executed"

print()
print("RESULT: PASS")
print("Executor crash leaves an executing state.")
print("Restart recovery detects the interrupted execution.")
print("Interrupted execution becomes failed, not successful.")
print("The action can subsequently enter the explicit retry lifecycle.")
