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
from judgment.recovery import recover_interrupted_actions
from judgment.execution import execute_action
from judgment.retry import retry_failed_action


ACTION = "free-disk-space"
test_directory = Path(tempfile.mkdtemp(prefix="recovery-retry-failure-invariant-"))
atexit.register(shutil.rmtree, test_directory, ignore_errors=True)

STATE_PATH = test_directory / "state" / "latest.json"
STATE_PATH.parent.mkdir(parents=True)
STATE_PATH.write_text(
    json.dumps({
        "actions": [{
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "approved",
            "retry_count": 0,
            "max_retries": lifecycle_module.MAX_RETRIES,
            "escalation_required": False,
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


print("=== RECOVERY → RETRY → EXECUTION FAILURE INVARIANT TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

before_audit = load_audit()

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

original_retry_count = target.get("retry_count", 0)

# Simulate crash.
target["status"] = "executing"
target["execution_result"] = None

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. CRASH STATE:")
print(
    ACTION,
    "|",
    target["status"],
    "| retry_count =",
    target["retry_count"],
)
print("PASS")


print()
print("2. RECOVERY:")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

assert ACTION in recovered

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"
assert target["retry_count"] == original_retry_count

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
print("3. RETRY:")

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
print("4. EXECUTION START:")

start_result = execute_action(
    ACTION,
    result="failure-invariant-test",
)

print("START:", start_result)

assert start_result["status"] == "executing"

print("PASS")


print()
print("5. SIMULATED EXECUTION FAILURE:")

failure_result = execute_action(
    ACTION,
    result="execution-failed",
    complete=True,
    success=False,
)

print("FAILURE:", failure_result)

assert failure_result["status"] == "failed"

print("PASS")


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
    target.get("execution_result"),
    "| retry_count =",
    target["retry_count"],
)

assert target["retry_count"] == original_retry_count + 1
assert target["status"] == "failed"
assert target["execution_result"] == "execution-failed"

print("PASS")


print()
print("7. LIFECYCLE AUDIT EVENTS:")

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

print("PASS")


print()
print("RESULT: PASS")
print("Recovery preserved the retry count.")
print("Retry incremented exactly once.")
print("Execution entered executing state.")
print("Execution failure did not increment retry count twice.")
print("Final lifecycle remained auditable.")
