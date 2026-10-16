import json

from judgment.audit import load_audit
from judgment.execution import execute_action
from judgment.lifecycle import (
    resolve_escalation,
    retry_failed_action,
)
from judgment.recovery import STATE_PATH


print("=== RESOLUTION → RETRY → FAILURE → RE-ESCALATION INVARIANT TEST ===")

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

before = load_audit()


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
print("2. EXPLICIT ESCALATION RESOLUTION:")

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
print("3. FIRST RETRY AFTER RESOLUTION:")

retry_one = retry_failed_action(ACTION)

print(retry_one)

assert retry_one["status"] == "blocked" or retry_one["status"] == "approved"

# Resolution already returns the action to approved.
# Therefore the first post-resolution execution is authorized directly.
if retry_one["status"] == "blocked":
    assert "Only failed actions" in retry_one["reason"]

    print(
        "Retry path correctly rejected because resolved action is already approved."
    )
else:
    assert retry_one["retry_count"] == 1

print("PASS")


print()
print("4. RE-AUTHORIZED EXECUTION:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

failure_one = execute_action(
    ACTION,
    result="post-resolution-first-failure",
    complete=True,
    success=False,
)

print("FAILURE:", failure_one)

assert failure_one["status"] == "failed"
assert failure_one["result"] == "post-resolution-first-failure"

print("PASS")


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

assert target["status"] == "failed"
assert target["retry_count"] == 0
assert target["escalation_required"] is False

print("PASS")


print()
print("5. FIRST POST-RESOLUTION RETRY:")

retry_one = retry_failed_action(ACTION)

print(retry_one)

assert retry_one["status"] == "approved"
assert retry_one["retry_count"] == 1
assert retry_one["escalation_required"] is False

print("PASS")


print()
print("6. SECOND EXECUTION → FAILURE:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

failure_two = execute_action(
    ACTION,
    result="post-resolution-second-failure",
    complete=True,
    success=False,
)

print("FAILURE:", failure_two)

assert failure_two["status"] == "failed"
assert failure_two["result"] == "post-resolution-second-failure"

state = json.loads(
    STATE_PATH.read_text()
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["retry_count"] == 1
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
print("7. SECOND POST-RESOLUTION RETRY:")

retry_two = retry_failed_action(ACTION)

print(retry_two)

assert retry_two["status"] == "approved"
assert retry_two["retry_count"] == 2
assert retry_two["escalation_required"] is False

print("PASS")


print()
print("8. THIRD EXECUTION → FAILURE:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

failure_three = execute_action(
    ACTION,
    result="post-resolution-third-failure",
    complete=True,
    success=False,
)

print("FAILURE:", failure_three)

assert failure_three["status"] == "failed"

print("PASS")


print()
print("9. RETRY EXHAUSTION → RE-ESCALATION:")

blocked = retry_failed_action(ACTION)

print(blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["max_retries"] == 2
assert blocked["escalation_required"] is True

print("PASS")


print()
print("10. FINAL DURABLE STATE:")

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
print("11. AUDIT LIFECYCLE:")

after = load_audit()

events = [
    event
    for event in after[len(before):]
    if event.get("action") == ACTION
]

for event in events:
    print(
        event.get("event"),
        "|",
        event.get("status"),
        "|",
        event.get("result"),
    )

observed = {
    event.get("event")
    for event in events
}

assert "escalation-resolved" in observed
assert "execution-started" in observed
assert "execution-failed" in observed
assert "retry-approved" in observed
assert "retry-blocked" in observed

print("PASS")


print()
print("12. FINAL RE-ESCALATION INVARIANT:")

print("EXPLICIT RESOLUTION RESET THE RETRY BUDGET")
print("POST-RESOLUTION EXECUTION WAS AUTHORIZED")
print("EXECUTION FAILURES DID NOT DOUBLE-CONSUME RETRIES")
print("RETRY COUNT REACHED THE NEW MAXIMUM")
print("RETRY EXHAUSTION RE-ESCALATED THE ACTION")
print("OLD ESCALATION DID NOT CONTAMINATE THE RESOLVED LIFECYCLE")
print("FINAL STATE AND AUDIT REMAINED DURABLE")

print()
print("RESULT: PASS")
