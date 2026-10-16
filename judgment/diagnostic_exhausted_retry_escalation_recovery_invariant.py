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
from judgment.recovery import recover_interrupted_actions
from judgment.retry import retry_failed_action


print("=== EXHAUSTED RETRY → ESCALATION → RECOVERY INVARIANT TEST ===")


ACTION = "free-disk-space"
test_directory = Path(tempfile.mkdtemp(prefix="exhausted-retry-escalation-"))
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
            "execution_result": "initial-failure",
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


state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

target["status"] = "failed"
target["execution_result"] = "initial-failure"
target["retry_count"] = 0
target["max_retries"] = 2
target["escalation_required"] = False

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

before_audit = load_audit()


print()
print("1. INITIAL FAILED STATE:")
print(
    ACTION,
    "|",
    target["status"],
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)
print("PASS")


print()
print("2. FIRST RETRY:")

result = retry_failed_action(ACTION)

print(result)

assert result["status"] == "approved"
assert result["retry_count"] == 1

print("PASS")


print()
print("3. FIRST EXECUTION FAILURE:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="first-execution-failure",
    complete=True,
    success=False,
)

print("FAILURE:", failure)

assert failure["status"] == "failed"

print("PASS")


print()
print("4. SECOND RETRY:")

result = retry_failed_action(ACTION)

print(result)

assert result["status"] == "approved"
assert result["retry_count"] == 2

print("PASS")


print()
print("5. SECOND EXECUTION FAILURE:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="second-execution-failure",
    complete=True,
    success=False,
)

print("FAILURE:", failure)

assert failure["status"] == "failed"

print("PASS")


print()
print("6. RETRY EXHAUSTION:")

blocked = retry_failed_action(ACTION)

print(blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["escalation_required"] is True

print("PASS")


print()
print("7. SIMULATED CRASH STATE:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

target["status"] = "executing"
target["execution_result"] = None

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print(
    ACTION,
    "|",
    target["status"],
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

assert target["retry_count"] == 2
assert target["escalation_required"] is True

print("PASS")


print()
print("8. RECOVERY:")

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

print(
    ACTION,
    "|",
    target["status"],
    "|",
    target["execution_result"],
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"
assert target["retry_count"] == 2
assert target["escalation_required"] is True

print("PASS")


print()
print("9. POST-RECOVERY RETRY:")

blocked = retry_failed_action(ACTION)

print(blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["escalation_required"] is True

print("PASS")


print()
print("10. FINAL DURABLE STATE:")

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
print("11. AUDIT LIFECYCLE:")

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

observed = [event.get("event") for event in new_events]

required = {
    "retry-approved",
    "execution-started",
    "execution-failed",
    "retry-blocked",
    "recovery-interrupted",
}

assert required.issubset(set(observed))

print("PASS")


print()
print("12. FINAL INVARIANT:")

assert target["retry_count"] == 2
assert target["max_retries"] == 2
assert target["escalation_required"] is True
assert target["status"] == "failed"

print("RETRY BUDGET REMAINED EXHAUSTED")
print("ESCALATION SURVIVED RECOVERY")
print("POST-RECOVERY RETRY REMAINED BLOCKED")
print("NO RETRY BUDGET WAS SILENTLY RESTORED")

print("PASS")


print()
print("RESULT: PASS")
print("Retry exhaustion remained durable.")
print("Escalation remained durable across recovery.")
print("Recovery converted the interrupted execution to failed.")
print("Post-recovery retry remained blocked.")
print("The complete lifecycle remained auditable.")
