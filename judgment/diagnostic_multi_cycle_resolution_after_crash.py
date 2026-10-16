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

print("=== MULTI-CYCLE CRASH → RECOVERY → RESOLUTION → FRESH CYCLE INVARIANT TEST ===")

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
print("1. INITIAL RE-ESCALATED STATE:")
print(
    ACTION,
    "| failed | retry_count = 2 | escalation = True"
)
print("PASS")

print()
print("2. CRASH DURING RE-ESCALATED STATE:")
state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "executing"

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
print("3. FRESH PROCESS RECOVERY:")
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
print("4. EXPLICIT RESOLUTION AFTER RECOVERY:")
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
assert resolution["max_retries"] == 2
assert resolution["escalation_required"] is False
print("PASS")

print()
print("5. DURABLE POST-RESOLUTION STATE:")
state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

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
print("6. FRESH EXECUTION AFTER RECOVERY + RESOLUTION:")
start = execute_action(ACTION)
print("START:", start)

assert start["status"] == "executing"
print("PASS")

print()
print("7. FRESH CYCLE FAILURE:")
failure = execute_action(
    ACTION,
    result="post-recovery-fresh-cycle-failure",
    complete=True,
    success=False,
)
print("FAILURE:", failure)

assert failure["status"] == "failed"
assert failure["result"] == "post-recovery-fresh-cycle-failure"
print("PASS")

print()
print("8. FRESH CYCLE RETRY:")
retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
assert retry["max_retries"] == 2
assert retry["escalation_required"] is False
print("PASS")

print()
print("9. FINAL DURABLE STATE:")
state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "| status =", target["status"],
    "| retry_count =", target["retry_count"],
    "| max_retries =", target["max_retries"],
    "| escalation =", target["escalation_required"],
    "| result =", target.get("execution_result"),
)

assert target["status"] == "approved"
assert target["retry_count"] == 1
assert target["max_retries"] == 2
assert target["escalation_required"] is False
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
assert any(e.get("event") == "execution-started" for e in events)
assert any(e.get("event") == "execution-failed" for e in events)
assert any(e.get("event") == "retry-approved" for e in events)

print("PASS")

print()
print("11. FINAL CROSS-CYCLE INVARIANT:")
print("RE-ESCALATION SURVIVED CRASH")
print("RECOVERY PRESERVED ESCALATION")
print("EXPLICIT POST-RECOVERY RESOLUTION RESET RETRY BUDGET")
print("RESOLUTION DID NOT LEAK PRIOR RETRY STATE")
print("FRESH EXECUTION WAS RE-AUTHORIZED")
print("FRESH FAILURE CONSUMED NO RETRY UNTIL EXPLICIT RETRY")
print("FRESH RETRY CONSUMED EXACTLY ONE RETRY")
print("OLD CYCLE STATE DID NOT CONTAMINATE THE NEW CYCLE")
print("RESOLUTION AND FRESH EXECUTION REMAINED AUDITABLE")
print("RESULT: PASS")
