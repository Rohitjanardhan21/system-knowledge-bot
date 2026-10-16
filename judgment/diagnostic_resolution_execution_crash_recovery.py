import json

from judgment.audit import load_audit
from judgment.execution import execute_action
from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.lifecycle import resolve_escalation


print("=== RESOLUTION → RE-AUTHORIZED EXECUTION → CRASH → RECOVERY INVARIANT TEST ===")

ACTION = "free-disk-space"

state = json.loads(
    STATE_PATH.read_text()
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

target["status"] = "failed"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = "retry-limit-reached"

STATE_PATH.write_text(
    json.dumps(state, indent=2)
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


print()
print("2. EXPLICIT RESOLUTION:")

resolved = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)

print(resolved)

assert resolved["status"] == "approved"
assert resolved["retry_count"] == 0
assert resolved["escalation_required"] is False

print("PASS")


print()
print("3. RE-AUTHORIZED EXECUTION:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

state = json.loads(
    STATE_PATH.read_text()
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["status"] == "executing"
assert target["retry_count"] == 0
assert target["escalation_required"] is False

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
print("4. SIMULATED CRASH DURING RE-AUTHORIZED EXECUTION:")

state["actions"] = [
    {
        **a,
        "status": "executing",
    }
    if a.get("action") == ACTION
    else a
    for a in state["actions"]
]

STATE_PATH.write_text(
    json.dumps(state, indent=2)
)

print(
    ACTION,
    "| executing",
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

print("PASS")


print()
print("5. FRESH PROCESS RECOVERY:")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

assert ACTION in recovered

state = json.loads(
    STATE_PATH.read_text()
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"
assert target["retry_count"] == 0
assert target["escalation_required"] is False

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

print("PASS")


print()
print("6. POST-RECOVERY RETRY:")

retry_result = __import__(
    "judgment.lifecycle",
    fromlist=["retry_failed_action"]
).retry_failed_action(ACTION)

print(retry_result)

assert retry_result["status"] == "approved"
assert retry_result["retry_count"] == 1
assert retry_result["escalation_required"] is False

print("PASS")


print()
print("7. FINAL DURABLE STATE:")

state = json.loads(
    STATE_PATH.read_text()
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
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

assert target["status"] == "approved"
assert target["retry_count"] == 1
assert target["escalation_required"] is False

print("PASS")


print()
print("8. FINAL INVARIANT:")
print("RESOLUTION RESTORED AUTHORITY")
print("CRASH DID NOT RESTORE ESCALATION")
print("RECOVERY PRESERVED THE RESOLVED AUTHORIZATION")
print("RECOVERY CONVERTED INTERRUPTED EXECUTION TO FAILED")
print("ONLY AN EXPLICIT RETRY CONSUMED RETRY BUDGET")
print("RESULT: PASS")
