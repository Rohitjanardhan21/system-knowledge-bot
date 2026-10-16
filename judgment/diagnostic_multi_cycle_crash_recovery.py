import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json

from judgment.audit import load_audit
from judgment.execution import execute_action
from judgment.lifecycle import resolve_escalation, retry_failed_action
from judgment.recovery import recover_interrupted_actions

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== MULTI-CYCLE ESCALATION → CRASH → RECOVERY DURABILITY INVARIANT TEST ===")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "failed"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = "retry-limit-reached"

open(STATE_PATH, "w", encoding="utf-8").write(json.dumps(state, indent=2))
before = load_audit()

print()
print("1. FIRST ESCALATION:")
print(ACTION, "| failed | retry_count = 2 | escalation = True")
print("PASS")

print()
print("2. FIRST RESOLUTION:")
r1 = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)
print(r1)
assert r1["status"] == "approved"
assert r1["retry_count"] == 0
assert r1["escalation_required"] is False
print("PASS")

print()
print("3. FIRST EXECUTION → FAILURE:")
start = execute_action(ACTION)
print("START:", start)
assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="cycle-1-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)
assert failure["status"] == "failed"
print("PASS")

print()
print("4. FIRST RETRY:")
retry = retry_failed_action(ACTION)
print(retry)
assert retry["status"] == "approved"
assert retry["retry_count"] == 1
print("PASS")

print()
print("5. SECOND EXECUTION → FAILURE:")
start = execute_action(ACTION)
print("START:", start)
assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="cycle-1-retry-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)
assert failure["status"] == "failed"
print("PASS")

print()
print("6. SECOND RETRY:")
retry = retry_failed_action(ACTION)
print(retry)
assert retry["status"] == "approved"
assert retry["retry_count"] == 2
print("PASS")

print()
print("7. THIRD EXECUTION → FAILURE:")
start = execute_action(ACTION)
print("START:", start)
assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="cycle-1-final-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)
assert failure["status"] == "failed"
print("PASS")

print()
print("8. RE-ESCALATION:")
blocked = retry_failed_action(ACTION)
print(blocked)
assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["escalation_required"] is True
print("PASS")

print()
print("9. CRASH DURING RE-ESCALATED STATE:")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "executing"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True

open(STATE_PATH, "w", encoding="utf-8").write(json.dumps(state, indent=2))

print(
    ACTION,
    "| executing | retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)
print("PASS")

print()
print("10. FRESH PROCESS RECOVERY:")
recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
    "| retry_count =",
    target["retry_count"],
    "| escalation =",
    target["escalation_required"],
)

assert target["status"] == "failed"
assert target["retry_count"] == 2
assert target["escalation_required"] is True
assert target["execution_result"] == "interrupted-by-restart"
print("PASS")

print()
print("11. POST-RECOVERY RETRY GUARD:")
blocked = retry_failed_action(ACTION)
print(blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["escalation_required"] is True
print("PASS")

print()
print("12. FINAL DURABLE STATE:")
state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "| status =", target["status"],
    "| result =", target["execution_result"],
    "| retry_count =", target["retry_count"],
    "| max_retries =", target["max_retries"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] == "failed"
assert target["retry_count"] == 2
assert target["max_retries"] == 2
assert target["escalation_required"] is True
print("PASS")

print()
print("13. AUDIT LIFECYCLE:")
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

assert any(e.get("event") == "escalation-resolved" for e in events)
assert any(e.get("event") == "execution-failed" for e in events)
assert any(e.get("event") == "retry-approved" for e in events)
assert any(e.get("event") == "retry-blocked" for e in events)
assert any(e.get("event") == "recovery-interrupted" for e in events)

print("PASS")

print()
print("14. FINAL MULTI-CYCLE CRASH/RECOVERY INVARIANT:")
print("FIRST ESCALATION RESOLUTION RESET THE RETRY BUDGET")
print("MULTIPLE RETRIES CONSUMED THE NEW BUDGET CORRECTLY")
print("RE-ESCALATION OCCURRED ONLY AFTER RETRY EXHAUSTION")
print("CRASH DID NOT CLEAR RE-ESCALATION")
print("RECOVERY PRESERVED RETRY EXHAUSTION")
print("POST-RECOVERY RETRY REMAINED BLOCKED")
print("NO AUTHORIZATION WAS MANUFACTURED BY RECOVERY")
print("FINAL STATE AND AUDIT REMAINED DURABLE")
print("RESULT: PASS")
