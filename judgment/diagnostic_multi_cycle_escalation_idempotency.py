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

print("=== MULTI-CYCLE ESCALATION IDEMPOTENCY INVARIANT TEST ===")

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
print("1. INITIAL ESCALATED STATE:")
print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
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
print("3. FIRST RESOLUTION IDEMPOTENCY CHECK:")
r1_again = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)
print(r1_again)

assert r1_again["status"] == "blocked"
assert r1_again["escalation_required"] is False
print("PASS")

print()
print("4. EXECUTION AFTER FIRST RESOLUTION:")
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
print("5. FIRST RETRY:")
retry1 = retry_failed_action(ACTION)
print(retry1)

assert retry1["status"] == "approved"
assert retry1["retry_count"] == 1
print("PASS")

print()
print("6. SECOND FAILURE:")
execute_action(ACTION)

failure2 = execute_action(
    ACTION,
    result="cycle-1-retry-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure2)

assert failure2["status"] == "failed"
print("PASS")

print()
print("7. SECOND RETRY:")
retry2 = retry_failed_action(ACTION)
print(retry2)

assert retry2["status"] == "approved"
assert retry2["retry_count"] == 2
print("PASS")

print()
print("8. FINAL FAILURE → RE-ESCALATION:")
execute_action(ACTION)

failure3 = execute_action(
    ACTION,
    result="cycle-1-final-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure3)

assert failure3["status"] == "failed"

blocked = retry_failed_action(ACTION)
print("RE-ESCALATION:", blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["escalation_required"] is True
print("PASS")

print()
print("9. SECOND RESOLUTION:")
r2 = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)
print(r2)

assert r2["status"] == "approved"
assert r2["retry_count"] == 0
assert r2["escalation_required"] is False
print("PASS")

print()
print("10. SECOND RESOLUTION IDEMPOTENCY:")
r2_again = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)
print(r2_again)

assert r2_again["status"] == "blocked"
assert r2_again["retry_count"] == 0
assert r2_again["escalation_required"] is False
print("PASS")

print()
print("11. FINAL DURABLE STATE:")
state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "| status =", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] == "approved"
assert target["retry_count"] == 0
assert target["escalation_required"] is False
print("PASS")

print()
print("12. AUDIT IDEMPOTENCY:")
after = load_audit()

events = [
    e for e in after[len(before):]
    if e.get("action") == ACTION
]

resolution_events = [
    e for e in events
    if e.get("event") == "escalation-resolved"
]

assert len(resolution_events) == 2

for event in resolution_events:
    assert event["status"] == "approved"
    assert event["result"] == "escalation-resolved"
    assert event["retry_count"] == 0
    assert event["escalation_required"] is False

print("ESCALATION-RESOLVED EVENTS:", len(resolution_events))
print("PASS")

print()
print("13. FINAL MULTI-CYCLE INVARIANT:")
print("FIRST RESOLUTION RESET RETRY BUDGET")
print("FIRST RESOLUTION WAS IDEMPOTENT")
print("FIRST RETRY CYCLE RE-ESCALATED CORRECTLY")
print("SECOND RESOLUTION RESET A FRESH RETRY BUDGET")
print("SECOND RESOLUTION WAS IDEMPOTENT")
print("NO RETRY STATE LEAKED BETWEEN ESCALATION CYCLES")
print("EXACTLY TWO RESOLUTION AUDIT EVENTS EXIST")
print("RESULT: PASS")
