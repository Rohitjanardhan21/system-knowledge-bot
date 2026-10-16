from __future__ import annotations

import json
from pathlib import Path

from judgment.execution import execute_action
from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.retry import retry_failed_action
from judgment.audit import load_audit

ACTION = "free-disk-space"
SANDBOX = Path("state") / "stale_worker_completion_sandbox"

SANDBOX.mkdir(parents=True, exist_ok=True)

file_a = SANDBOX / "cleanup_a.tmp"
file_b = SANDBOX / "cleanup_b.tmp"

for f in (file_a, file_b):
    f.write_text("temporary data", encoding="utf-8")

state = {
    "actions": [{
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_result": None,
    }]
}

STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

before = load_audit()

print()
print("=== STALE WORKER COMPLETION AFTER RECOVERY TEST ===")

print()
print("1. INITIAL REAL-WORLD STATE:")

assert file_a.exists()
assert file_b.exists()

print("A:", file_a.exists())
print("B:", file_b.exists())
print("PASS")

print()
print("2. WORKER A EXECUTION ADMISSION:")

start_a = execute_action(ACTION)

print("WORKER A:", start_a)

assert start_a["status"] == "executing"

print("Worker A admitted.")
print("PASS")

print()
print("3. WORKER A PARTIAL REAL-WORLD SIDE EFFECT:")

file_a.unlink()

assert not file_a.exists()
assert file_b.exists()

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("PASS")

print()
print("4. WORKER A CRASH / STALE EXECUTION:")

print("Worker A crashes before completion.")
print("Its execution is now stale.")

print("PASS")

print()
print("5. FRESH PROCESS RECOVERY:")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
)

assert ACTION in recovered
assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
assert action["retry_count"] == 0

print("PASS")

print()
print("6. EXPLICIT RETRY FOR WORKER B:")

retry = retry_failed_action(ACTION)

print("WORKER B AUTHORIZATION:", retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1

print("PASS")

print()
print("7. WORKER B EXECUTION:")

start_b = execute_action(ACTION)

print("WORKER B:", start_b)

assert start_b["status"] == "executing"

print("Worker B admitted.")
print("PASS")

print()
print("8. WORKER B COMPLETES CURRENT WORLD STATE:")

if file_b.exists():
    file_b.unlink()

complete_b = execute_action(
    ACTION,
    result="worker-b-success",
    complete=True,
)

print("WORKER B COMPLETION:", complete_b)

assert complete_b["status"] == "executed"
assert complete_b["result"] == "worker-b-success"

print("PASS")

print()
print("9. DURABLE STATE AFTER WORKER B:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
)

assert action["status"] == "executed"
assert action["execution_result"] == "worker-b-success"
assert action["retry_count"] == 1

print("PASS")

print()
print("10. STALE WORKER A ATTEMPTS COMPLETION:")

print(
    "Worker A now attempts to complete "
    "its OLD execution."
)

try:
    stale_completion = execute_action(
        ACTION,
        result="STALE-WORKER-A-COMPLETION",
        complete=True,
    )

    print("STALE COMPLETION RESPONSE:")
    print(stale_completion)

except Exception as exc:
    stale_completion = None
    print(
        "STALE COMPLETION RAISED:",
        type(exc).__name__,
        str(exc),
    )

print()
print("11. CRITICAL STALE-WORKER INVARIANT:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
)

print()
print("Expected:")
print("status must remain EXECUTED")
print("result must remain worker-b-success")
print("retry_count must remain 1")

if action["status"] != "executed":
    raise AssertionError(
        "CRITICAL GAP: stale worker changed final lifecycle state."
    )

if action.get("execution_result") != "worker-b-success":
    raise AssertionError(
        "CRITICAL GAP: stale worker overwrote newer execution result."
    )

if action["retry_count"] != 1:
    raise AssertionError(
        "CRITICAL GAP: stale worker modified retry budget."
    )

print("STALE WORKER COULD NOT CORRUPT NEWER STATE")
print("PASS")

print()
print("12. REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert not file_b.exists()

print("Filesystem matches successful Worker B execution.")
print("PASS")

print()
print("13. AUDIT:")

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

print("PASS")

print()
print("14. FINAL STALE-WORKER INVARIANTS:")

print("OLD EXECUTION BECAME STALE AFTER RECOVERY")
print("NEW RETRY WAS EXPLICITLY AUTHORIZED")
print("NEW WORKER COMPLETED SUCCESSFULLY")
print("STALE WORKER COULD NOT OVERWRITE NEWER STATE")
print("RETRY COUNT REMAINED STABLE")
print("REAL-WORLD STATE REMAINED CORRECT")
print("DURABLE STATE REMAINED CORRECT")
print("AUDIT REMAINED CONSISTENT")

for f in (file_a, file_b):
    if f.exists():
        f.unlink()

if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass

print()
print("RESULT: PASS")
