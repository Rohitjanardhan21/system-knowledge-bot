from pathlib import Path
import json

from judgment.lifecycle import (
    retry_failed_action,
    begin_execution,
    complete_execution,
)

STATE_PATH = Path("state") / "latest.json"

print("=== FAILED ACTION RETRY TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    action
    for action in state.get("actions", [])
    if action.get("action") == "free-disk-space"
)

# Establish a failed action.
target["status"] = "failed"
target["execution_result"] = "interrupted-by-restart"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print("FAILED:")
print(
    target.get("action"),
    "|",
    target.get("status"),
    "|",
    target.get("execution_result"),
)

# Explicit retry.
result = retry_failed_action(target)

print()
print("RETRY REQUEST:")
print(result)

assert result["status"] == "approved"
assert target["status"] == "approved"

# The action can now enter execution again.
result = begin_execution(target)

print()
print("RE-EXECUTION START:")
print(result)

assert result["status"] == "executing"
assert target["status"] == "executing"

# Complete successfully.
result = complete_execution(
    target,
    success=True,
    result="dry-run-success",
)

print()
print("RE-EXECUTION COMPLETE:")
print(result)

assert result["status"] == "executed"
assert target["status"] == "executed"

# Successful actions must still be protected.
result = retry_failed_action(target)

print()
print("RETRY EXECUTED ACTION:")
print(result)

assert result["status"] == "blocked"

print()
print("RESULT: PASS")
print("Failed actions require explicit retry.")
print("Retried actions return through approved → executing.")
print("Successfully executed actions remain non-retryable.")
