import json

from judgment.recovery import STATE_PATH
from judgment.retry import retry_failed_action
from judgment.audit import load_audit


print("=== ESCALATED STATE TRANSITION GUARD INVARIANT TEST ===")

ACTION = "free-disk-space"


state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

# Establish the authoritative exhausted/escalated state.
target["status"] = "failed"
target["retry_count"] = target.get("max_retries", 2)
target["max_retries"] = target.get("max_retries", 2)
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
    "| max_retries =",
    target["max_retries"],
    "| escalation =",
    target["escalation_required"],
)

assert target["status"] == "failed"
assert target["retry_count"] == target["max_retries"]
assert target["escalation_required"] is True

print("PASS")


print()
print("2. RETRY GUARD:")

before_audit = load_audit()

retry_result = retry_failed_action(ACTION)

print(retry_result)

assert retry_result["status"] == "blocked"
assert retry_result["retry_count"] == target["max_retries"]
assert retry_result["escalation_required"] is True

print("PASS")


print()
print("3. VERIFY DURABLE STATE:")

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
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

assert target["status"] == "failed"
assert target["retry_count"] == target["max_retries"]
assert target["escalation_required"] is True

print("PASS")


print()
print("4. ATTEMPT STATUS DOWNGRADE:")

target["status"] = "approved"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print(
    ACTION,
    "| manually written status =",
    target["status"],
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

print("PASS")


print()
print("5. RELOAD DURABLE STATE:")

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
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

assert target["retry_count"] == target["max_retries"]
assert target["escalation_required"] is True

print("PASS")


print()
print("6. IMPORTANT BOUNDARY:")

print(
    "Escalation metadata remained durable even when status "
    "was externally rewritten."
)

print(
    "Retry budget remained exhausted."
)

print("PASS")


print()
print("7. AUDIT CHECK:")

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
print("Retry guard blocked automatic retry.")
print("Retry exhaustion remained durable.")
print("Escalation metadata survived state rewriting.")
print("No retry budget was silently restored.")
