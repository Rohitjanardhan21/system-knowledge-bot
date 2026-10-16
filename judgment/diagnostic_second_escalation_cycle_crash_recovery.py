import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json

from judgment.execution import execute_action
from judgment.lifecycle import resolve_escalation, retry_failed_action
from judgment.audit import load_audit
from judgment.recovery import recover_interrupted_actions

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== SECOND ESCALATION CYCLE → CRASH → RECOVERY INVARIANT TEST ===")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "failed"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = "second-escalation"

open(STATE_PATH, "w", encoding="utf-8").write(json.dumps(state, indent=2))

before = load_audit()

print("\n1. INITIAL SECOND ESCALATION:")
print(ACTION, "| failed | retry_count = 2 | escalation = True")
print("PASS")

print("\n2. RESOLVE SECOND ESCALATION:")
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

print("\n3. EXECUTE AFTER SECOND RESOLUTION:")
start = execute_action(ACTION)
print("START:", start)

assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="second-cycle-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)

assert failure["status"] == "failed"
print("PASS")

print("\n4. RETRY AFTER SECOND RESOLUTION:")
retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
assert retry["escalation_required"] is False
print("PASS")

print("\n5. SECOND RETRY CYCLE FAILURE:")
start = execute_action(ACTION)
print("START:", start)

assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="second-cycle-retry-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)

assert failure["status"] == "failed"
print("PASS")

print("\n6. FINAL RETRY → FAILURE → RE-ESCALATION:")
retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 2

start = execute_action(ACTION)
print("START:", start)

assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="second-cycle-final-retry-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)

assert failure["status"] == "failed"

blocked = retry_failed_action(ACTION)
print("RE-ESCALATION:", blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["escalation_required"] is True

print("PASS")

print("\n7. SECOND ESCALATION IS DURABLE:")
state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "| status =", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)

assert target["retry_count"] == 2
assert target["escalation_required"] is True
print("PASS")

print("\n8. CRASH DURING SECOND ESCALATION:")
target["status"] = "executing"

open(STATE_PATH, "w", encoding="utf-8").write(
    json.dumps(state, indent=2)
)

recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "| status =", target["status"],
    "| result =", target.get("execution_result"),
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] == "failed"
assert target["retry_count"] == 2
assert target["escalation_required"] is True
print("PASS")

print("\n9. POST-RECOVERY RETRY GUARD:")
blocked = retry_failed_action(ACTION)
print(blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["escalation_required"] is True
print("PASS")

print("\n10. AUDIT LIFECYCLE:")
after = load_audit()

events = [
    e for e in after[len(before):]
    if e.get("action") == ACTION
]

for event in events:
    print(
        event.get("event"),
        "|",
        event.get("status"),
        "|",
        event.get("result"),
    )

resolved = [
    e for e in events
    if e.get("event") == "escalation-resolved"
]

recovery = [
    e for e in events
    if e.get("event") == "recovery-interrupted"
]

assert len(resolved) == 1
assert len(recovery) == 1
assert any(e.get("event") == "retry-blocked" for e in events)

print("PASS")

print("\n11. FINAL INVARIANT:")
print("SECOND ESCALATION CYCLE STARTED WITH A FRESH RETRY BUDGET")
print("SECOND CYCLE EXHAUSTION RE-ESCALATED THE ACTION")
print("CRASH DID NOT CLEAR SECOND ESCALATION")
print("RECOVERY DID NOT RESTORE RETRY AUTHORITY")
print("RETRY COUNT REMAINED AT 2")
print("ESCALATION REMAINED DURABLE")
print("RESULT: PASS")
