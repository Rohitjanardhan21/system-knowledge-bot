from __future__ import annotations

import json

from judgment.recovery import STATE_PATH
from judgment.executor import execute_plan
from judgment.audit import load_audit
import judgment.action_handlers as handlers


print("=== FAILURE → EXPLICIT RETRY → SUCCESS TEST ===")


def reset_state():
    state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    for action in state.get("actions", []):
        if action.get("action") == "free-disk-space":
            action["status"] = "approved"
            action["execution_result"] = None
            action.pop("execution_started_at", None)
            action.pop("execution_completed_at", None)
            action.pop("recovery_reason", None)

    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


reset_state()

plan = [{
    "action": "free-disk-space",
    "priority": "high",
    "execution_mode": "automatic",
    "status": "approved",
}]

facts = {
    "memory": {"utilization": 92},
    "disk": {"utilization": 93},
}


# ---------------------------------------------------------
# 1. INJECT FAILURE
# ---------------------------------------------------------

original_handler = handlers.execute_action_handler


def failing_handler(action, dry_run=True):
    raise RuntimeError("simulated-first-attempt-failure")


handlers.execute_action_handler = failing_handler

print()
print("1. FIRST EXECUTION — INJECTED FAILURE:")

try:
    results = execute_plan(
        plan,
        dry_run=True,
        current_facts=facts,
    )

    print(results)

finally:
    handlers.execute_action_handler = original_handler


state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)

assert target["status"] == "failed"

print("PASS")


# ---------------------------------------------------------
# 2. VERIFY IMPLICIT RETRY IS BLOCKED
# ---------------------------------------------------------

print()
print("2. IMPLICIT RETRY ATTEMPT:")

blocked = execute_plan(
    plan,
    dry_run=True,
    current_facts=facts,
)

print(blocked)

assert blocked[0]["status"] == "blocked"
assert blocked[0]["result"] == "retry-required"

print("PASS")


# ---------------------------------------------------------
# 3. EXPLICITLY RESET TO APPROVED
# ---------------------------------------------------------

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "approved"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("3. EXPLICIT RETRY APPROVAL:")
print(
    target["action"],
    "|",
    target["status"],
)

assert target["status"] == "approved"

print("PASS")


# ---------------------------------------------------------
# 4. SUCCESSFUL RETRY
# ---------------------------------------------------------

print()
print("4. SUCCESSFUL RETRY:")

results = execute_plan(
    plan,
    dry_run=True,
    current_facts=facts,
)

print(results)

assert results[0]["status"] == "simulated"
assert results[0]["lifecycle_status"] == "executed"

print("PASS")


# ---------------------------------------------------------
# 5. FINAL PERSISTED STATE
# ---------------------------------------------------------

print()
print("5. FINAL PERSISTED STATE:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)

assert target["status"] == "executed"

print("PASS")


# ---------------------------------------------------------
# 6. DUPLICATE EXECUTION
# ---------------------------------------------------------

print()
print("6. DUPLICATE EXECUTION:")

duplicate = execute_plan(
    plan,
    dry_run=True,
    current_facts=facts,
)

print(duplicate)

assert duplicate[0]["status"] == "blocked"
assert duplicate[0]["result"] == "already-executed"

print("PASS")


# ---------------------------------------------------------
# 7. AUDIT
# ---------------------------------------------------------

print()
print("7. AUDIT:")

audit = load_audit()

events = [
    event
    for event in audit
    if event.get("action") == "free-disk-space"
]

for event in events[-10:]:
    print(event)


assert any(
    e.get("event") == "execution-failed"
    and e.get("result") == "RuntimeError: simulated-first-attempt-failure"
    for e in events
)

assert any(
    e.get("event") == "execution-completed"
    and e.get("status") == "executed"
    for e in events
)

print("PASS")


print()
print("RESULT: PASS")
print("Failed execution became failed.")
print("Implicit retry was blocked.")
print("Explicit approval was required before retry.")
print("Retry successfully reached executed.")
print("Duplicate execution remained blocked.")
print("Failure and successful retry remained auditable.")
