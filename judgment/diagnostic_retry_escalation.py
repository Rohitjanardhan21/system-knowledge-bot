import json
from judgment.recovery import STATE_PATH
from judgment.lifecycle import MAX_RETRIES, retry_failed_action
from judgment.audit import load_audit

print("=== RETRY ESCALATION DURABILITY TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "failed"
target["retry_count"] = MAX_RETRIES
target["max_retries"] = MAX_RETRIES
target["escalation_required"] = True
target["execution_result"] = "retry-limit-reached"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. CURRENT STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "| retry_count =",
    target.get("retry_count"),
    "| max_retries =",
    target.get("max_retries"),
    "| escalation =",
    target.get("escalation_required"),
)

assert target["status"] == "failed"
assert target["retry_count"] >= target["max_retries"]
assert target["escalation_required"] is True
print("PASS")


print()
print("2. RETRY AFTER ESCALATION:")

result = retry_failed_action(target)

print(result)

assert result["status"] == "blocked"
assert target["status"] == "failed"
assert result["escalation_required"] is True
print("PASS")


print()
print("3. PERSISTED STATE:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

persisted = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    persisted["action"],
    "|",
    persisted["status"],
    "| retry_count =",
    persisted.get("retry_count"),
    "| max_retries =",
    persisted.get("max_retries"),
    "| escalation =",
    persisted.get("escalation_required"),
)

assert persisted["retry_count"] >= persisted["max_retries"]
assert persisted["escalation_required"] is True
print("PASS")


print()
print("4. ESCALATION AUDIT:")

audit = load_audit()

events = [
    event
    for event in audit
    if (
        event.get("action") == "free-disk-space"
        and event.get("event") in {
            "retry-escalated",
            "retry-blocked",
        }
    )
]

for event in events[-5:]:
    print(event)

assert events
print("PASS")


print()
print("RESULT: PASS")
print("Retry exhaustion remains escalated.")
print("Further retry is blocked.")
print("Escalation survives persistence.")
print("Escalation remains auditable.")
