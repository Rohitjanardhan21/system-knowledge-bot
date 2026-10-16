import json

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH, recover_interrupted_actions


print("=== RECOVERY STATE ↔ AUDIT INVARIANT TEST ===")


state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

before_audit = load_audit()


# Force several actions into executing state.
targets = [
    "free-disk-space",
    "restart-service",
    "clear-cache",
]

for action in targets:
    target = next(
        a for a in state["actions"]
        if a.get("action") == action
    )

    target["status"] = "executing"
    target["execution_result"] = None


STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)


print()
print("1. INITIAL EXECUTING ACTIONS:")

for action in targets:
    target = next(
        a for a in state["actions"]
        if a.get("action") == action
    )

    print(
        target["action"],
        "|",
        target["status"],
    )

print("PASS")


print()
print("2. RECOVERY:")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

for action in targets:
    assert action in recovered

print("PASS")


print()
print("3. FINAL STATE:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

for action in targets:
    target = next(
        a for a in state["actions"]
        if a.get("action") == action
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
print("4. RECOVERY AUDIT EVENTS:")

after_audit = load_audit()

new_events = after_audit[len(before_audit):]

recovery_events = [
    event
    for event in new_events
    if event.get("event") == "recovery-interrupted"
]

for event in recovery_events:
    print(event)

for action in targets:
    matches = [
        event
        for event in recovery_events
        if event.get("action") == action
    ]

    assert len(matches) == 1

    event = matches[0]

    assert event.get("status") == "failed"
    assert event.get("result") == "interrupted-by-restart"

print("PASS")


print()
print("5. STATE ↔ AUDIT INVARIANT:")

for action in targets:

    target = next(
        a for a in state["actions"]
        if a.get("action") == action
    )

    matching_events = [
        event
        for event in recovery_events
        if event.get("action") == action
    ]

    event = matching_events[0]

    assert target["status"] == event["status"]
    assert target["execution_result"] == event["result"]

    print(
        action,
        "| STATE:",
        target["status"],
        "| AUDIT:",
        event["status"],
        "|",
        target["execution_result"],
        "=",
        event["result"],
    )

print("PASS")


print()
print("RESULT: PASS")
print("Every recovered action has exactly one recovery audit event.")
print("Recovery audit status matches durable action state.")
print("Recovery result matches durable execution result.")
print("State and audit remain mutually consistent.")
