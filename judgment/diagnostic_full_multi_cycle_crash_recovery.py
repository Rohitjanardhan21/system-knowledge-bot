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

print("=== FULL MULTI-CYCLE → CRASH → RECOVERY → RESOLUTION → RE-ESCALATION INVARIANT TEST ===")

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
print(ACTION, "| failed | retry_count = 2 | escalation = True")
print("PASS")

print()
print("2. CRASH → RECOVERY:")
start = execute_action(ACTION)
assert start["status"] == "blocked"

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "executing"
open(STATE_PATH, "w", encoding="utf-8").write(json.dumps(state, indent=2))

recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

assert target["status"] == "failed"
assert target["retry_count"] == 2
assert target["escalation_required"] is True
print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

print()
print("3. RESOLVE AFTER RECOVERY:")
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
print("4. FRESH CYCLE → FAILURE:")
start = execute_action(ACTION)
print("START:", start)
assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="fresh-cycle-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)
assert failure["status"] == "failed"
assert failure["result"] == "fresh-cycle-failure"
print("PASS")

print()
print("5. RETRY 1 → FAILURE:")
retry1 = retry_failed_action(ACTION)
print("RETRY:", retry1)
assert retry1["status"] == "approved"
assert retry1["retry_count"] == 1

start = execute_action(ACTION)
assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="fresh-cycle-retry-1-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)
assert failure["status"] == "failed"
print("PASS")

print()
print("6. RETRY 2 → FAILURE:")
retry2 = retry_failed_action(ACTION)
print("RETRY:", retry2)
assert retry2["status"] == "approved"
assert retry2["retry_count"] == 2

start = execute_action(ACTION)
assert start["status"] == "executing"

failure = execute_action(
    ACTION,
    result="fresh-cycle-retry-2-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)
assert failure["status"] == "failed"
print("PASS")

print()
print("7. RETRY EXHAUSTION → RE-ESCALATION:")
blocked = retry_failed_action(ACTION)
print("RE-ESCALATION:", blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["escalation_required"] is True
print("PASS")

print()
print("8. CRASH DURING SECOND ESCALATION:")
state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "executing"
open(STATE_PATH, "w", encoding="utf-8").write(json.dumps(state, indent=2))

recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

assert target["status"] == "failed"
assert target["retry_count"] == 2
assert target["escalation_required"] is True
assert target["execution_result"] == "interrupted-by-restart"

print(
    ACTION,
    "|", target["status"],
    "|", target["execution_result"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

print()
print("9. POST-RECOVERY AUTHORITY GUARD:")
blocked = retry_failed_action(ACTION)
print(blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["escalation_required"] is True
print("PASS")

print()
print("10. AUDIT LIFECYCLE:")
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

assert any(e.get("event") == "recovery-interrupted" for e in events)
assert any(e.get("event") == "escalation-resolved" for e in events)
assert any(e.get("event") == "retry-approved" for e in events)
assert any(e.get("event") == "retry-blocked" for e in events)

print("PASS")

print()
print("11. FINAL CROSS-CYCLE INVARIANT:")
print("FIRST ESCALATION SURVIVED CRASH AND RECOVERY")
print("EXPLICIT RESOLUTION RESET THE RETRY BUDGET")
print("FRESH CYCLE WAS RE-AUTHORIZED")
print("FRESH RETRIES CONSUMED THE NEW BUDGET")
print("RE-ESCALATION OCCURRED ONLY AFTER EXHAUSTION")
print("SECOND ESCALATION SURVIVED CRASH AND RECOVERY")
print("RECOVERY DID NOT MANUFACTURE AUTHORIZATION")
print("RETRY REMAINED BLOCKED AFTER SECOND RECOVERY")
print("CROSS-CYCLE STATE REMAINED DURABLE")
print("AUDIT LIFECYCLE REMAINED COMPLETE")

print()
print("RESULT: PASS")
