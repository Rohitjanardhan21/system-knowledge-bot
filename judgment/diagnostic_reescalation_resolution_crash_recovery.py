import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json
from datetime import datetime, timedelta, timezone

from judgment.execution import execute_action
from judgment.lifecycle import resolve_escalation
from judgment.audit import load_audit
from judgment.recovery import recover_interrupted_actions

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== RE-ESCALATION → RESOLUTION → CRASH → RECOVERY INVARIANT TEST ===")

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
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

print()
print("2. EXPLICIT RESOLUTION:")
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
print("3. SIMULATED CRASH DURING RE-AUTHORIZED EXECUTION:")
start = execute_action(ACTION)
print("START:", start)

assert start["status"] == "executing"

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

assert target["status"] == "executing"
assert target["retry_count"] == 0
assert target["escalation_required"] is False
target["execution_started_at"] = (
    datetime.now(timezone.utc) - timedelta(minutes=6)
).isoformat()
open(STATE_PATH, "w", encoding="utf-8").write(
    json.dumps(state, indent=2)
)

print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

print()
print("4. FRESH PROCESS RECOVERY:")
recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "|", target["status"],
    "|", target.get("execution_result"),
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] == "failed"
assert target["retry_count"] == 0
assert target["escalation_required"] is False
print("PASS")

print()
print("5. SECOND EXPLICIT RESOLUTION ATTEMPT:")
resolution2 = resolve_escalation(
    ACTION,
    principal={
        "scope": "admin",
        "_source": "api_key",
        "name": "judgment-test-admin",
    },
)
print(resolution2)

assert resolution2["status"] == "blocked"
assert resolution2["escalation_required"] is False
print("PASS")

print()
print("6. POST-RECOVERY RETRY:")
from judgment.lifecycle import retry_failed_action

retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
assert retry["escalation_required"] is False
print("PASS")

print()
print("7. AUDIT LIFECYCLE:")
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

resolved_events = [
    e for e in events
    if e.get("event") == "escalation-resolved"
]

recovery_events = [
    e for e in events
    if e.get("event") == "recovery-interrupted"
]

assert len(resolved_events) == 1
assert len(recovery_events) == 1
assert any(e.get("event") == "retry-approved" for e in events)

print("PASS")

print()
print("8. FINAL INVARIANT:")
print("RESOLUTION RESTORED AUTHORITY")
print("CRASH DURING RE-AUTHORIZED EXECUTION DID NOT RESTORE ESCALATION")
print("RECOVERY PRESERVED RESOLVED AUTHORIZATION")
print("SECOND RESOLUTION DID NOT MANUFACTURE AUTHORITY")
print("POST-RECOVERY RETRY CONSUMED EXACTLY ONE RETRY")
print("EXACTLY ONE ESCALATION-RESOLVED EVENT EXISTS")
print("RESULT: PASS")
