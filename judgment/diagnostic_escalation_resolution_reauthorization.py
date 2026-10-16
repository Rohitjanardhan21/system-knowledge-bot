import json

from judgment.recovery import STATE_PATH
from judgment.retry import retry_failed_action
from judgment.execution import execute_action
from judgment.lifecycle import resolve_escalation
from judgment._test_auth import ADMIN_PRINCIPAL


print("=== ESCALATION RESOLUTION → RE-AUTHORIZATION INVARIANT TEST ===")

ACTION = "free-disk-space"

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

# Establish exhausted/escalated state.
target["status"] = "failed"
target["retry_count"] = target.get("max_retries", 2)
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


print()
print("2. RETRY BEFORE ESCALATION RESOLUTION:")

result = retry_failed_action(ACTION)

print(result)

assert result["status"] == "blocked"
assert result["retry_count"] == target["retry_count"]
assert result["escalation_required"] is True

print("PASS")


print()
print("3. EXPLICIT ESCALATION RESOLUTION:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

resolution = resolve_escalation(
    ACTION,
    principal=ADMIN_PRINCIPAL,
)
assert resolution["status"] == "approved"

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
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
print("PASS")


print()
print("4. RE-AUTHORIZED EXECUTION:")

start = execute_action(
    ACTION,
    result="post-escalation-resolution-success",
)

print("START:", start)

assert start["status"] == "executing"

complete = execute_action(
    ACTION,
    result="post-escalation-resolution-success",
    complete=True,
)

print("COMPLETE:", complete)

assert complete["status"] == "executed"

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
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

assert target["status"] == "executed"
assert target["execution_result"] == "post-escalation-resolution-success"
assert target["retry_count"] == 0
assert target["escalation_required"] is False

print("PASS")


print()
print("RESULT: PASS")
print("Escalated state could not be bypassed by retry.")
print("Execution authority was restored only through explicit resolution.")
print("Resolved state permitted execution.")
print("Final successful state was durable.")
