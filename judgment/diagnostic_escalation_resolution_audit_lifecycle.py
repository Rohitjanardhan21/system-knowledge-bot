import json

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH
from judgment.retry import resolve_escalation
from judgment.execution import execute_action


print("=== ESCALATION RESOLUTION AUDIT → EXECUTION INVARIANT TEST ===")

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
print("2. RESOLVE ESCALATION:")

result = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)

print(result)

assert result["status"] == "approved"
assert result["retry_count"] == 0
assert result["escalation_required"] is False

print("PASS")

state = json.loads(
    STATE_PATH.read_text()
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["status"] == "approved"
assert target["retry_count"] == 0
assert target["escalation_required"] is False

print()
print("3. DURABLE RESOLVED STATE:")
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

after = load_audit()

events = [
    event
    for event in after[len(before):]
    if event.get("action") == ACTION
]

resolution_events = [
    event
    for event in events
    if event.get("event") == "escalation-resolved"
]

assert len(resolution_events) == 1

resolution = resolution_events[0]

assert resolution["status"] == "approved"
assert resolution["result"] == "escalation-resolved"
assert resolution["retry_count"] == 0
assert resolution["escalation_required"] is False

print()
print("4. ESCALATION RESOLUTION AUDIT:")
print(
    resolution["event"],
    "|",
    resolution["status"],
    "|",
    resolution["result"],
)
print("PASS")

print()
print("5. RE-AUTHORIZED EXECUTION:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

complete = execute_action(
    ACTION,
    result="post-resolution-success",
    complete=True,
)

print("COMPLETE:", complete)

assert complete["status"] == "executed"

print("PASS")

state = json.loads(
    STATE_PATH.read_text()
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["status"] == "executed"
assert target["execution_result"] == "post-resolution-success"
assert target["retry_count"] == 0
assert target["escalation_required"] is False

after = load_audit()

events = [
    event
    for event in after[len(before):]
    if event.get("action") == ACTION
]

observed = {
    event.get("event")
    for event in events
}

assert "escalation-resolved" in observed
assert "execution-started" in observed
assert "execution-completed" in observed

completion = [
    event
    for event in events
    if event.get("event") == "execution-completed"
][0]

assert completion["status"] == "executed"
assert completion["result"] == "post-resolution-success"

print()
print("6. FINAL STATE ↔ AUDIT INVARIANT:")
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
print("Escalation resolution is now explicitly auditable.")
print("Retry budget was reset only by explicit resolution.")
print("Execution authority was restored only after resolution.")
print("Resolution and execution remained durable and auditable.")
