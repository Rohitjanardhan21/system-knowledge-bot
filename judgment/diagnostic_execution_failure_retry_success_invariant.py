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
test_directory = Path(tempfile.mkdtemp(prefix="execution-failure-retry-success-"))
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
            "execution_result": "execution-failed",
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


print("=== EXECUTION FAILURE → RETRY → SUCCESS INVARIANT TEST ===")

before_audit = load_audit()

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

target["status"] = "failed"
target["execution_result"] = "execution-failed"

original_retry_count = target.get("retry_count", 0)

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


print()
print("2. RETRY:")

retry_result = retry_failed_action(ACTION)

print(retry_result)

assert retry_result["status"] == "approved"

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["status"] == "approved"
assert target["retry_count"] == original_retry_count + 1

print(
    ACTION,
    "|",
    target["status"],
    "| retry_count =",
    target["retry_count"],
)
print("PASS")


print()
print("3. RE-EXECUTION:")

start_result = execute_action(
    ACTION,
    result="retry-success",
)

print("START:", start_result)

assert start_result["status"] == "executing"


complete_result = execute_action(
    ACTION,
    result="retry-success",
    complete=True,
)

print("COMPLETE:", complete_result)

assert complete_result["status"] == "executed"

print("PASS")


print()
print("4. FINAL DURABLE STATE:")

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
    target.get("execution_result"),
    "| retry_count =",
    target["retry_count"],
)

assert target["status"] == "executed"
assert target["execution_result"] == "retry-success"
assert target["retry_count"] == original_retry_count + 1

print("PASS")


print()
print("5. AUDIT LIFECYCLE:")

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


observed_events = {
    event.get("event")
    for event in new_events
}

assert "retry-approved" in observed_events
assert "execution-started" in observed_events
assert "execution-completed" in observed_events

print("PASS")


print()
print("6. SUCCESS BOUNDARY:")

completion_events = [
    event
    for event in new_events
    if event.get("event") == "execution-completed"
]

assert len(completion_events) == 1

completion = completion_events[0]

assert completion["status"] == "executed"
assert completion["result"] == "retry-success"

assert target["status"] == completion["status"]
assert target["execution_result"] == completion["result"]

print(
    "STATE:",
    target["status"],
    "| AUDIT:",
    completion["status"],
)

print(
    "RESULT:",
    target["execution_result"],
    "=",
    completion["result"],
)

print("PASS")


print()
print("RESULT: PASS")
print("Execution failure was replaced by an explicit retry.")
print("Retry count increased exactly once.")
print("The second execution succeeded.")
print("Final durable state matches the completion audit.")
print("Failure from the previous attempt did not contaminate success.")
