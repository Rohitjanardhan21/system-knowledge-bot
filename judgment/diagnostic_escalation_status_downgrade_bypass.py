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
from judgment.lifecycle import begin_execution
from judgment.retry import retry_failed_action


print("=== ESCALATED STATE STATUS-DOWNGRADE BYPASS TEST ===")


ACTION = "free-disk-space"
test_directory = Path(tempfile.mkdtemp(prefix="escalation-status-downgrade-"))
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
            "retry_count": lifecycle_module.MAX_RETRIES,
            "max_retries": lifecycle_module.MAX_RETRIES,
            "escalation_required": True,
            "execution_result": "retry-limit-reached",
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


# Establish an exhausted, escalated state.
target["status"] = "failed"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = "retry-limit-reached"


STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)


print()
print("1. INITIAL ESCALATED STATE:")
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


# Simulate an external/manual status downgrade.
state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

target["status"] = "approved"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)


print()
print("2. EXTERNAL STATUS DOWNGRADE:")
print(
    ACTION,
    "| status =",
    target["status"],
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)
print("PASS")


print()
print("3. DIRECT EXECUTION ATTEMPT AFTER DOWNGRADE:")

execution_result = begin_execution(ACTION)

print(execution_result)

assert execution_result["status"] == "blocked"
assert execution_result["result"] == "retry-limit-reached"
assert execution_result["retry_count"] == 2
assert execution_result["max_retries"] == 2
assert execution_result["escalation_required"] is True

print("PASS")


print()
print("4. RETRY ATTEMPT AFTER DOWNGRADE:")

result = retry_failed_action(ACTION)

print(result)

assert result["status"] == "blocked"
assert result["retry_count"] == 2
assert result["max_retries"] == 2
assert result["escalation_required"] is True

print("PASS")


print()
print("5. FINAL DURABLE STATE:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

print(
    ACTION,
    "| status =",
    target["status"],
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

print("PASS")


print()
print("6. FINAL INVARIANT:")

assert target["retry_count"] == 2
assert target["max_retries"] == 2
assert target["escalation_required"] is True

print("ESCALATION CANNOT BE BYPASSED BY STATUS REWRITE")
print("EXHAUSTED RETRY BUDGET REMAINED EXHAUSTED")
print("STATUS DOWNGRADE DID NOT AUTHORIZE ANOTHER RETRY")
print("PASS")


print()
print("RESULT: PASS")
print("Escalation remained behaviorally enforced.")
print("Retry exhaustion could not be bypassed by rewriting status.")
print("Manual status downgrade did not restore retry authority.")
