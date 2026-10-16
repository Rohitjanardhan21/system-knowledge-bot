import json

from judgment.audit import load_audit
from judgment.lifecycle import resolve_escalation
from judgment.recovery import STATE_PATH


print("=== ESCALATION RESOLUTION IDEMPOTENCY INVARIANT TEST ===")

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
print("2. FIRST ESCALATION RESOLUTION:")

first = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)

print(first)

assert first["status"] == "approved"
assert first["retry_count"] == 0
assert first["escalation_required"] is False

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


after_first = load_audit()

first_events = [
    event
    for event in after_first[len(before):]
    if (
        event.get("action") == ACTION
        and event.get("event") == "escalation-resolved"
    )
]

assert len(first_events) == 1

print(
    "AUDIT EVENTS AFTER FIRST RESOLUTION:",
    len(first_events),
)

print("PASS")


print()
print("3. SECOND ESCALATION RESOLUTION:")

second = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)

print(second)

print("PASS")


print()
print("4. VERIFY SECOND RESOLUTION DID NOT CHANGE STATE:")

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
assert target["retry_count"] == 0
assert target["escalation_required"] is False

print("PASS")


print()
print("5. AUDIT IDEMPOTENCY:")

after_second = load_audit()

resolution_events = [
    event
    for event in after_second[len(before):]
    if (
        event.get("action") == ACTION
        and event.get("event") == "escalation-resolved"
    )
]

print(
    "ESCALATION-RESOLVED EVENTS:",
    len(resolution_events),
)

assert len(resolution_events) == 1

print("No duplicate resolution event was generated.")
print("PASS")


print()
print("6. RESOLUTION EVENT CONTENT:")

resolution = resolution_events[0]

print(
    resolution["event"],
    "|",
    resolution["status"],
    "|",
    resolution["result"],
    "| retry_count =",
    resolution["retry_count"],
    "| escalation =",
    resolution["escalation_required"],
)

assert resolution["status"] == "approved"
assert resolution["result"] == "escalation-resolved"
assert resolution["retry_count"] == 0
assert resolution["escalation_required"] is False

print("PASS")


print()
print("7. FINAL IDEMPOTENCY INVARIANT:")

print("FIRST RESOLUTION: authorization restored")
print("SECOND RESOLUTION: no additional state transition")
print("RETRY COUNT REMAINED 0")
print("ESCALATION REMAINED CLEARED")
print("EXACTLY ONE RESOLUTION AUDIT EVENT EXISTS")

print()
print("RESULT: PASS")
print("Escalation resolution is idempotent.")
print("Repeated resolution does not manufacture authorization.")
print("Repeated resolution does not reset retry state repeatedly.")
print("Resolution audit history remains idempotent.")
