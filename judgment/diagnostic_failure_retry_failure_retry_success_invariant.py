import atexit
import json
import shutil
import tempfile
from pathlib import Path

import judgment.audit as audit_module
import judgment.execution as execution_module
import judgment.lifecycle as lifecycle_module
import judgment.recovery as recovery_module
import judgment.state_lock as state_lock_module
from judgment.audit import load_audit
from judgment.retry import retry_failed_action
from judgment.execution import execute_action


ACTION = "free-disk-space"
test_directory = Path(tempfile.mkdtemp(prefix="failure-retry-success-invariant-"))
atexit.register(shutil.rmtree, test_directory, ignore_errors=True)

STATE_PATH = test_directory / "state" / "latest.json"
STATE_PATH.parent.mkdir(parents=True)
STATE_PATH.write_text(
    json.dumps({
        "actions": [{
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "failed",
            "retry_count": 0,
            "max_retries": lifecycle_module.MAX_RETRIES,
            "escalation_required": False,
            "execution_result": "first-failure",
        }],
    }, indent=2),
    encoding="utf-8",
)

recovery_module.STATE_PATH = STATE_PATH
lifecycle_module.STATE_PATH = STATE_PATH
execution_module.STATE_PATH = STATE_PATH
state_lock_module.STATE_LOCK_PATH = STATE_PATH.parent / "state.lock"

audit_module.AUDIT_PATH = STATE_PATH.parent / "audit.json"
audit_module.AUDIT_TEMP_PATH = audit_module.AUDIT_PATH.with_suffix(".tmp")
audit_module.AUDIT_LOCK_PATH = audit_module.AUDIT_PATH.with_suffix(".lock")


print("=== FAILURE → RETRY → FAILURE → RETRY → SUCCESS INVARIANT TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

before_audit = load_audit()

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

original_retry_count = target.get("retry_count", 0)

# Start from a clean failed attempt.
target["status"] = "failed"
target["execution_result"] = "first-failure"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. INITIAL FAILED STATE:")
print(
    ACTION,
    "|",
    target["status"],
    "|",
    target["execution_result"],
    "| retry_count =",
    target["retry_count"],
)
print("PASS")


# ---------------------------------------------------------
# FIRST RETRY
# ---------------------------------------------------------

print()
print("2. FIRST RETRY:")

retry1 = retry_failed_action(ACTION)

print(retry1)

assert retry1["status"] == "approved"
assert retry1["retry_count"] == original_retry_count + 1

print("PASS")


# ---------------------------------------------------------
# FIRST RE-EXECUTION → FAILURE
# ---------------------------------------------------------

print()
print("3. FIRST RE-EXECUTION → FAILURE:")

start1 = execute_action(
    ACTION,
    result="first-reexecution",
)

print("START:", start1)

assert start1["status"] == "executing"

failure1 = execute_action(
    ACTION,
    result="second-failure",
    complete=True,
    success=False,
)

print("FAILURE:", failure1)

assert failure1["status"] == "failed"

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["status"] == "failed"
assert target["execution_result"] == "second-failure"
assert target["retry_count"] == original_retry_count + 1

print(
    ACTION,
    "|",
    target["status"],
    "|",
    target["execution_result"],
    "| retry_count =",
    target["retry_count"],
)

print("PASS")


# ---------------------------------------------------------
# SECOND RETRY
# ---------------------------------------------------------

print()
print("4. SECOND RETRY:")

retry2 = retry_failed_action(ACTION)

print(retry2)

assert retry2["status"] == "approved"
assert retry2["retry_count"] == original_retry_count + 2

print("PASS")


# ---------------------------------------------------------
# SECOND RE-EXECUTION → SUCCESS
# ---------------------------------------------------------

print()
print("5. SECOND RE-EXECUTION → SUCCESS:")

start2 = execute_action(
    ACTION,
    result="final-success",
)

print("START:", start2)

assert start2["status"] == "executing"

success = execute_action(
    ACTION,
    result="final-success",
    complete=True,
)

print("COMPLETE:", success)

assert success["status"] == "executed"

print("PASS")


# ---------------------------------------------------------
# FINAL STATE
# ---------------------------------------------------------

print()
print("6. FINAL DURABLE STATE:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

print(
    ACTION,
    "|",
    target["status"],
    "|",
    target["execution_result"],
    "| retry_count =",
    target["retry_count"],
)

assert target["status"] == "executed"
assert target["execution_result"] == "final-success"
assert target["retry_count"] == original_retry_count + 2

print("PASS")


# ---------------------------------------------------------
# AUDIT
# ---------------------------------------------------------

print()
print("7. AUDIT LIFECYCLE:")

after_audit = load_audit()

new_events = [
    event
    for event in after_audit[len(before_audit):]
    if event.get("action") == ACTION
]

for event in new_events:
    print(
        event.get("event"),
        "|",
        event.get("status"),
        "|",
        event.get("result"),
    )


required_events = [
    "retry-approved",
    "execution-started",
    "execution-failed",
    "retry-approved",
    "execution-started",
    "execution-completed",
]

observed_events = [
    event.get("event")
    for event in new_events
]

assert observed_events == required_events

print("PASS")


# ---------------------------------------------------------
# FAILURE/SUCCESS SEPARATION
# ---------------------------------------------------------

print()
print("8. FAILURE/SUCCESS SEPARATION:")

failure_events = [
    event
    for event in new_events
    if event.get("event") == "execution-failed"
]

completion_events = [
    event
    for event in new_events
    if event.get("event") == "execution-completed"
]

assert len(failure_events) == 1
assert len(completion_events) == 1

assert failure_events[0]["status"] == "failed"
assert failure_events[0]["result"] == "second-failure"

assert completion_events[0]["status"] == "executed"
assert completion_events[0]["result"] == "final-success"

print(
    "FAILURE:",
    failure_events[0]["status"],
    "|",
    failure_events[0]["result"],
)

print(
    "SUCCESS:",
    completion_events[0]["status"],
    "|",
    completion_events[0]["result"],
)

print("PASS")


print()
print("RESULT: PASS")
print("First retry incremented the retry budget exactly once.")
print("First re-execution failed without consuming another retry.")
print("Second retry incremented the retry budget exactly once.")
print("Final re-execution succeeded.")
print("Failure and success remained separate audit events.")
print("Final durable state matches the successful completion.")
