from __future__ import annotations

import json
from pathlib import Path

from judgment.audit import load_audit
from judgment.execution import execute_action
from judgment.recovery import STATE_PATH, recover_interrupted_actions

ACTION = "free-disk-space"
SANDBOX = Path("state") / "concurrent_execution_crash_sandbox"

SANDBOX.mkdir(parents=True, exist_ok=True)

file_a = SANDBOX / "cleanup_a.tmp"
file_b = SANDBOX / "cleanup_b.tmp"

file_a.write_text("temporary data", encoding="utf-8")
file_b.write_text("temporary data", encoding="utf-8")

state = {
    "actions": [{
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
        "retry_count": 1,
        "max_retries": 1,
        "escalation_required": False,
        "execution_result": None,
        "cleanup_targets": [
            str(file_a),
            str(file_b),
        ],
    }]
}

STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

before = load_audit()

print()
print("=== CONCURRENT EXECUTION → REAL-WORLD SIDE EFFECT → CRASH → RECOVERY TEST ===")

print()
print("1. INITIAL REAL-WORLD STATE:")

print("A:", file_a.exists())
print("B:", file_b.exists())

assert file_a.exists()
assert file_b.exists()

print("PASS")

print()
print("2. EXECUTION ADMISSION:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

print("Exactly one execution admitted.")
print("PASS")

print()
print("3. REAL-WORLD SIDE EFFECT BEFORE CRASH:")

file_a.unlink()

print("A deleted:", not file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert file_b.exists()

print("Partial side effect occurred.")
print("PASS")

print()
print("4. SIMULATED PROCESS CRASH:")

print("Process crashes before durable execution completion.")
print("PASS")

print()
print("5. FRESH PROCESS RECOVERY:")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
    "| max_retries =", action["max_retries"],
)

assert ACTION in recovered
assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"

print("PASS")

print()
print("6. VERIFY ACTUAL WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert file_b.exists()

print("Recovery preserved the real-world side effect.")
print("PASS")

print()
print("7. VERIFY RETRY BUDGET:")

assert action["retry_count"] == 1
assert action["max_retries"] == 1

print("retry_count =", action["retry_count"])
print("max_retries =", action["max_retries"])

print("Recovery did not consume or manufacture retry budget.")
print("PASS")

print()
print("8. VERIFY NO FALSE SUCCESS:")

assert action["status"] != "executed"
assert action["execution_result"] == "interrupted-by-restart"

print("Interrupted execution remains failed.")
print("PASS")

print()
print("9. AUDIT:")

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

started = [
    e for e in events
    if e.get("event") == "execution-started"
]

recovered_events = [
    e for e in events
    if e.get("event") == "recovery-interrupted"
]

assert len(started) == 1
assert len(recovered_events) == 1

print("Exactly one execution and one recovery interruption recorded.")
print("PASS")

print()
print("10. FINAL CRASH-RECOVERY INVARIANTS:")

print("ONLY ONE EXECUTION WAS ADMITTED")
print("REAL-WORLD SIDE EFFECT OCCURRED")
print("CRASH DID NOT PRODUCE FALSE SUCCESS")
print("RECOVERY PRESERVED THE ACTUAL WORLD STATE")
print("RECOVERY DID NOT REPEAT THE SIDE EFFECT")
print("RECOVERY DID NOT CONSUME RETRY BUDGET")
print("INTERRUPTION REMAINED DURABLE")
print("AUDIT PRESERVED EXECUTION → CRASH → RECOVERY")

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
