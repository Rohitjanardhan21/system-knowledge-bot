import json
from pathlib import Path

from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.lifecycle import retry_failed_action
from judgment.audit import load_audit

print("=== ESCALATION → CRASH/RECOVERY SAFETY TEST ===")


def get_target():
    state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )
    return next(
        a for a in state["actions"]
        if a.get("action") == "free-disk-space"
    )


# --------------------------------------------------
# 1. ESTABLISH ESCALATED STATE
# --------------------------------------------------

target = get_target()

target["status"] = "failed"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = "retry-limit-exhausted"

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

for action in state["actions"]:
    if action.get("action") == "free-disk-space":
        action.update(target)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. ESCALATED STATE:")
print(
    target["action"],
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


# --------------------------------------------------
# 2. SIMULATE CRASH-DURING-EXECUTION MARKER
# --------------------------------------------------

target["status"] = "executing"

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

for action in state["actions"]:
    if action.get("action") == "free-disk-space":
        action.update(target)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("2. SIMULATED CRASH STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

assert target["status"] == "executing"
print("PASS")


# --------------------------------------------------
# 3. FRESH-PROCESS RECOVERY
# --------------------------------------------------

print()
print("3. RECOVERY:")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

target = get_target()

print(
    target["action"],
    "|",
    target["status"],
    "|",
    target["execution_result"],
    "| retry_count =",
    target.get("retry_count"),
    "| escalation =",
    target.get("escalation_required"),
)

assert "free-disk-space" in recovered
assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"

# Critical invariant:
# recovery must NOT erase retry exhaustion.
assert target["retry_count"] == 2
assert target["max_retries"] == 2
assert target["escalation_required"] is True

print("PASS")


# --------------------------------------------------
# 4. RETRY ATTEMPT AFTER RECOVERY
# --------------------------------------------------

print()
print("4. RETRY AFTER RECOVERY:")

result = retry_failed_action(target)

print(result)

assert result["status"] == "blocked"
assert result["retry_count"] == 2
assert result["max_retries"] == 2
assert result["escalation_required"] is True

print("PASS")


# --------------------------------------------------
# 5. FINAL DURABLE STATE
# --------------------------------------------------

print()
print("5. FINAL PERSISTED STATE:")

target = get_target()

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
assert target["retry_count"] == 2
assert target["max_retries"] == 2
assert target["escalation_required"] is True

print("PASS")


# --------------------------------------------------
# 6. AUDIT
# --------------------------------------------------

print()
print("6. AUDIT EVENTS:")

audit = load_audit()

events = [
    event
    for event in audit
    if event.get("action") == "free-disk-space"
    and event.get("event") in {
        "recovery-interrupted",
        "retry-blocked",
    }
]

for event in events[-5:]:
    print(event)

assert any(
    event.get("event") == "recovery-interrupted"
    for event in events
)

assert any(
    event.get("event") == "retry-blocked"
    and event.get("result") == "retry-limit-reached"
    for event in events
)

print("PASS")


print()
print("RESULT: PASS")
print("Crash recovery preserved retry exhaustion.")
print("Escalation survived recovery.")
print("Post-recovery retry remained blocked.")
print("Escalation remained durable and auditable.")
