import json

from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.lifecycle import (
    MAX_RETRIES,
    begin_execution,
    complete_execution,
    retry_failed_action,
)
from judgment.audit import load_audit

print("=== CRASH → RECOVERY → RETRY → SUCCESS TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Start from a clean failed/retryable state.
target["status"] = "executing"
target["retry_count"] = 0
target["max_retries"] = MAX_RETRIES
target["escalation_required"] = False
target.pop("execution_result", None)
target.pop("execution_completed_at", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

audit_before = len(load_audit())

print()
print("1. CRASH STATE:")
print(target["action"], "|", target["status"])
print("PASS")

print()
print("2. RECOVERY:")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

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
assert target["execution_result"] == "interrupted-by-restart"
print("PASS")

print()
print("3. EXPLICIT RETRY:")

retry = retry_failed_action(
    target,
    current_facts={
        "memory": {"utilization": 92},
        "disk": {"utilization": 93},
    },
)

print(retry)

assert retry["status"] == "approved"
assert target["status"] == "approved"
print("PASS")

print()
print("4. RE-EXECUTION:")

start = begin_execution(target)

print("START:", start)

assert start["status"] == "executing"

complete = complete_execution(
    target,
    success=True,
    result="post-recovery-success",
)

print("COMPLETE:", complete)

assert complete["status"] == "executed"
print("PASS")

print()
print("5. FINAL STATE:")

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
assert target["execution_result"] == "post-recovery-success"

print("PASS")

print()
print("6. AUDIT LIFECYCLE:")

audit = load_audit()
new_events = audit[audit_before:]

for event in new_events:
    if event.get("action") == "free-disk-space":
        print(
            event.get("event"),
            "|",
            event.get("status"),
            "|",
            event.get("result"),
        )

names = [
    event.get("event")
    for event in new_events
    if event.get("action") == "free-disk-space"
]

required = [
    "recovery-interrupted",
    "retry-approved",
    "execution-started",
    "execution-completed",
]

positions = []

for name in required:
    assert name in names, f"Missing audit event: {name}"
    positions.append(names.index(name))

assert positions == sorted(positions), (
    f"Lifecycle audit order incorrect: {positions}"
)

print("PASS")

print()
print("RESULT: PASS")
print("Crash recovery produced a failed action.")
print("Explicit retry restored the action to approved.")
print("Re-execution succeeded.")
print("Final state is executed.")
print("Recovery → retry → execution is fully auditable.")
