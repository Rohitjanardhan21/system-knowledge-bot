import json

from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.retry import retry_failed_action
from judgment.audit import load_audit


print("=== ESCALATION DURABILITY / NO-DOWNGRADE INVARIANT TEST ===")

ACTION = "free-disk-space"

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

# Establish already-exhausted state.
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
assert target["retry_count"] == target["max_retries"]
assert target["escalation_required"] is True
print("PASS")


print()
print("2. RETRY ATTEMPT:")

retry_result = retry_failed_action(ACTION)

print(retry_result)

assert retry_result["status"] == "blocked"
assert retry_result["retry_count"] == target["max_retries"]
assert retry_result["escalation_required"] is True

print("PASS")


print()
print("3. DURABLE STATE AFTER BLOCK:")

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
print("4. SIMULATED CRASH:")

target["status"] = "executing"

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

print("PASS")


print()
print("5. RECOVERY:")

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
print("6. POST-RECOVERY RETRY:")

retry_result = retry_failed_action(ACTION)

print(retry_result)

assert retry_result["status"] == "blocked"
assert retry_result["retry_count"] == target["max_retries"]
assert retry_result["escalation_required"] is True

print("PASS")


print()
print("7. FINAL INVARIANT:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

assert target["retry_count"] == target["max_retries"]
assert target["escalation_required"] is True

print("RETRY COUNT NEVER DECREASED")
print("ESCALATION NEVER CLEARED")
print("RECOVERY DID NOT DOWNGRADE ESCALATED STATE")
print("POST-RECOVERY RETRY REMAINED BLOCKED")
print("PASS")


print()
print("RESULT: PASS")
print("Escalation remained durable.")
print("Retry exhaustion remained irreversible through recovery.")
print("No state transition silently downgraded the action.")
