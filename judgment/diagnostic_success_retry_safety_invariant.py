import json

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH
from judgment.retry import retry_failed_action


print("=== SUCCESS → RETRY SAFETY INVARIANT TEST ===")


ACTION = "free-disk-space"


state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)


original_retry_count = target.get("retry_count", 0)
target["status"] = "executed"
target["execution_result"] = "successful-terminal-state"


STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)


before_audit = load_audit()


print()
print("1. INITIAL SUCCESS STATE:")
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
print("2. RETRY ATTEMPT:")

retry_result = retry_failed_action(ACTION)

print(retry_result)

assert retry_result["status"] == "blocked"

print("PASS")


print()
print("3. FINAL DURABLE STATE:")

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
)

assert target["status"] == "executed"
assert target["execution_result"] == "successful-terminal-state"
assert target["retry_count"] == original_retry_count

print("PASS")


print()
print("4. AUDIT CHECK:")

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

retry_events = [
    event
    for event in new_events
    if event.get("action") == ACTION
    and event.get("event") in {
        "retry-approved",
        "retry-blocked",
    }
]

assert not retry_events

print("No retry lifecycle event was generated.")
print("PASS")


print()
print("5. TERMINAL SUCCESS INVARIANT:")

assert target["status"] == "executed"
assert target["execution_result"] == "successful-terminal-state"
assert target["retry_count"] == original_retry_count

print("SUCCESSFUL ACTION REMAINED TERMINAL")
print("RETRY DID NOT ALTER DURABLE STATE")
print("PASS")


print()
print("RESULT: PASS")
print("Executed state cannot be retried through the failed-action retry path.")
print("Retry count remained unchanged.")
print("Successful execution remained durable.")
print("No retry lifecycle event was manufactured.")
