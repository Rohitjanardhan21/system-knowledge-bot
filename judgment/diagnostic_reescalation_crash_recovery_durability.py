import json

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.retry import retry_failed_action
from judgment.execution import execute_action
from judgment.lifecycle import MAX_RETRIES


print("=== RE-ESCALATION → CRASH → RECOVERY DURABILITY INVARIANT TEST ===")

ACTION = "free-disk-space"

state = json.loads(STATE_PATH.read_text())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "failed"
target["retry_count"] = MAX_RETRIES
target["max_retries"] = MAX_RETRIES
target["escalation_required"] = True
target["execution_result"] = "post-resolution-third-failure"

STATE_PATH.write_text(json.dumps(state, indent=2))

before = load_audit()

print()
print("1. INITIAL RE-ESCALATED STATE:")
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
print("2. RETRY GUARD BEFORE CRASH:")

blocked = retry_failed_action(ACTION)

print(blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == MAX_RETRIES
assert blocked["escalation_required"] is True

print("PASS")

print()
print("3. SIMULATED CRASH DURING ESCALATED STATE:")

state = json.loads(STATE_PATH.read_text())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "executing"

STATE_PATH.write_text(json.dumps(state, indent=2))

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
print("4. FRESH PROCESS RECOVERY:")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

assert ACTION in recovered

state = json.loads(STATE_PATH.read_text())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"
assert target["retry_count"] == MAX_RETRIES
assert target["escalation_required"] is True

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
print("5. POST-RECOVERY RETRY GUARD:")

blocked_after_recovery = retry_failed_action(ACTION)

print(blocked_after_recovery)

assert blocked_after_recovery["status"] == "blocked"
assert blocked_after_recovery["retry_count"] == MAX_RETRIES
assert blocked_after_recovery["escalation_required"] is True

print("PASS")

print()
print("6. FINAL DURABLE STATE:")

state = json.loads(STATE_PATH.read_text())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "|",
    target["status"],
    "|",
    target["execution_result"],
    "| retry_count =",
    target["retry_count"],
    "| max_retries =",
    target["max_retries"],
    "| escalation =",
    target["escalation_required"],
)

assert target["status"] == "failed"
assert target["retry_count"] == MAX_RETRIES
assert target["max_retries"] == MAX_RETRIES
assert target["escalation_required"] is True

print("PASS")

print()
print("7. AUDIT LIFECYCLE:")

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

observed = {event.get("event") for event in events}

assert "retry-blocked" in observed
assert "recovery-interrupted" in observed

print("PASS")

print()
print("8. RE-ESCALATION CRASH/RECOVERY INVARIANT:")

assert target["retry_count"] == MAX_RETRIES
assert target["escalation_required"] is True
assert target["status"] == "failed"

print("RE-ESCALATION SURVIVED CRASH")
print("RECOVERY DID NOT CLEAR ESCALATION")
print("RETRY BUDGET REMAINED EXHAUSTED")
print("POST-RECOVERY RETRY REMAINED BLOCKED")
print("NO AUTHORIZATION WAS MANUFACTURED BY RECOVERY")
print("FINAL STATE REMAINED DURABLE AND AUDITABLE")

print()
print("RESULT: PASS")
