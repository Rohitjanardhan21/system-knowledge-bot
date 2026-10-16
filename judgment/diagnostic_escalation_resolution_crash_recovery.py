import json
from datetime import datetime, timedelta, timezone

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.retry import resolve_escalation


print("=== ESCALATION RESOLUTION → CRASH → RECOVERY INVARIANT TEST ===")

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
print("2. SIMULATED RESOLUTION CRASH:")

# Simulate an interrupted resolution boundary.
# The authoritative state remains escalated.
state = json.loads(
    STATE_PATH.read_text()
)

target = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

target["status"] = "executing"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = None
target["execution_started_at"] = (
    datetime.now(timezone.utc) - timedelta(minutes=6)
).isoformat()

STATE_PATH.write_text(
    json.dumps(state, indent=2)
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
print("3. FRESH PROCESS RECOVERY:")

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
assert target["retry_count"] == 2
assert target["max_retries"] == 2
assert target["escalation_required"] is True
assert target["execution_result"] == "interrupted-by-restart"

print(
    ACTION,
    "|",
    target["status"],
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
    "| result =",
    target["execution_result"],
)

print("PASS")


print()
print("4. POST-RECOVERY RETRY GUARD:")

from judgment.retry import retry_failed_action

retry_result = retry_failed_action(ACTION)

print(retry_result)

assert retry_result["status"] == "blocked"
assert retry_result["retry_count"] == 2
assert retry_result["max_retries"] == 2
assert retry_result["escalation_required"] is True

print("PASS")


print()
print("5. ESCALATION RESOLUTION AFTER RECOVERY:")

resolution = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)

print(resolution)

assert resolution["status"] == "approved"
assert resolution["retry_count"] == 0
assert resolution["escalation_required"] is False

print("PASS")


print()
print("6. FINAL DURABLE STATE:")

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
print("7. AUDIT LIFECYCLE:")

after = load_audit()

new_events = [
    event
    for event in after[len(before):]
    if event.get("action") == ACTION
]

for event in new_events:
    print(
        event.get("event"),
        "|",
        event.get("status"),
        "|",
        event.get("result"),
    )

observed = {
    event.get("event")
    for event in new_events
}

assert "recovery-interrupted" in observed
assert "retry-blocked" in observed
assert "escalation-resolved" in observed

print("PASS")


print()
print("8. FINAL INVARIANT:")

print("CRASH DID NOT SILENTLY RESOLVE ESCALATION")
print("RECOVERY PRESERVED RETRY EXHAUSTION")
print("RECOVERY PRESERVED ESCALATION")
print("POST-RECOVERY RETRY REMAINED BLOCKED")
print("EXPLICIT RESOLUTION RESTORED AUTHORITY")
print("RESOLUTION REMAINED AUDITABLE")

print("PASS")

print()
print("RESULT: PASS")
print("Escalation resolution remained crash-safe.")
print("No authorization was manufactured by recovery.")
print("Only explicit resolution restored execution authority.")
