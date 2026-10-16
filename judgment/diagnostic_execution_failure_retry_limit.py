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
from judgment.execution import execute_action
from judgment.retry import retry_failed_action


ACTION = "free-disk-space"
test_directory = Path(tempfile.mkdtemp(prefix="execution-failure-retry-limit-"))
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
            "execution_result": "previous-execution-failed",
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


print("=== EXECUTION FAILURE → RETRY → FAILURE → RETRY LIMIT TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

before_audit = load_audit()

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

# Start from a clean failed state with retry budget available.
target["status"] = "failed"
target["execution_result"] = "previous-execution-failed"
target["retry_count"] = 0
target["max_retries"] = 2
target["escalation_required"] = False

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
    "| retry_count =",
    target["retry_count"],
    "| max_retries =",
    target["max_retries"],
)
print("PASS")


print()
print("2. FIRST RETRY:")

retry1 = retry_failed_action(ACTION)

print(retry1)

assert retry1["status"] == "approved"
assert retry1["retry_count"] == 1

print("PASS")


print()
print("3. FIRST RE-EXECUTION:")

start1 = execute_action(
    ACTION,
    result="first-execution-failure",
)

print("START:", start1)

assert start1["status"] == "executing"

failure1 = execute_action(
    ACTION,
    result="first-execution-failure",
    complete=True,
    success=False,
)

print("FAILURE:", failure1)

assert failure1["status"] == "failed"
assert failure1["result"] == "first-execution-failure"

print("PASS")


state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["retry_count"] == 1


print()
print("4. SECOND RETRY:")

retry2 = retry_failed_action(ACTION)

print(retry2)

assert retry2["status"] == "approved"
assert retry2["retry_count"] == 2

print("PASS")


print()
print("5. SECOND RE-EXECUTION:")

start2 = execute_action(
    ACTION,
    result="second-execution-failure",
)

print("START:", start2)

assert start2["status"] == "executing"

failure2 = execute_action(
    ACTION,
    result="second-execution-failure",
    complete=True,
    success=False,
)

print("FAILURE:", failure2)

assert failure2["status"] == "failed"
assert failure2["result"] == "second-execution-failure"

print("PASS")


print()
print("6. FINAL RETRY ATTEMPT:")

retry3 = retry_failed_action(ACTION)

print(retry3)

assert retry3["status"] == "blocked"
assert retry3["retry_count"] == 2
assert retry3["max_retries"] == 2
assert retry3["escalation_required"] is True

print("PASS")


print()
print("7. FINAL DURABLE STATE:")

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
    "| max_retries =",
    target["max_retries"],
    "| escalation =",
    target["escalation_required"],
)

assert target["status"] == "failed"
assert target["retry_count"] == 2
assert target["max_retries"] == 2
assert target["escalation_required"] is True

print("PASS")


print()
print("8. AUDIT LIFECYCLE:")

after_audit = load_audit()

new_events = after_audit[len(before_audit):]

for event in new_events:
    if event.get("action") == ACTION:
        print(
            event.get("event"),
            "|",
            event.get("status"),
            "|",
            event.get("result"),
        )

required_events = {
    "retry-approved",
    "execution-started",
    "execution-failed",
    "retry-blocked",
}

observed_events = {
    event.get("event")
    for event in new_events
    if event.get("action") == ACTION
}

assert required_events.issubset(observed_events)

print("PASS")


print()
print("RESULT: PASS")
print("First retry succeeded.")
print("First execution failure remained failed.")
print("Second retry succeeded.")
print("Second execution failure remained failed.")
print("Retry count reached the configured maximum exactly.")
print("Third retry was blocked.")
print("Escalation became durable.")
print("Retry and execution failure lifecycle remained auditable.")
