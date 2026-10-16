import json
from pathlib import Path

from judgment.lifecycle import (
    begin_execution,
    complete_execution,
    retry_failed_action,
)
from judgment.recovery import recover_interrupted_actions
from judgment.audit import load_audit


ACTION = "free-disk-space"
STATE_PATH = Path("state") / "latest.json"
SANDBOX = Path("state") / "real_world_ambiguous_completion_sandbox"

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
print("=== CRASH-AFTER-SIDE-EFFECT / AMBIGUOUS-COMPLETION TEST ===")


print()
print("1. INITIAL REAL-WORLD STATE:")

print("A:", file_a.exists())
print("B:", file_b.exists())

assert file_a.exists()
assert file_b.exists()

print("PASS")


print()
print("2. EXECUTION ADMISSION:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

action = state["actions"][0]

start = begin_execution(action)

print("START:", start)

assert start["status"] == "executing"

print("PASS")


print()
print("3. REAL-WORLD SIDE EFFECT OCCURS:")

file_a.unlink()

assert not file_a.exists()
assert file_b.exists()

print("A deleted:", not file_a.exists())
print("B exists:", file_b.exists())
print("PASS")


print()
print("4. CRITICAL FAILURE WINDOW:")

print("Real-world side effect succeeded.")
print("Durable completion is intentionally NOT recorded.")
print("Simulated process crash.")

print("PASS")


print()
print("5. FRESH PROCESS RECOVERY:")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

assert ACTION in recovered

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

assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
assert action["retry_count"] == 0

print("PASS")


print()
print("6. VERIFY ACTUAL WORLD STATE AFTER RECOVERY:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert file_b.exists()

print("Recovery preserved the real-world side effect.")
print("PASS")


print()
print("7. EXPLICIT RETRY AUTHORIZATION:")

retry = retry_failed_action(ACTION)

print("RETRY:", retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1

print("PASS")


print()
print("8. RETRY EXECUTION:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

action = state["actions"][0]

start = begin_execution(action)

print("START:", start)

assert start["status"] == "executing"

print("Current filesystem state:")
print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert file_b.exists()

print("PASS")


print()
print("9. RECONCILE CURRENT WORLD:")

print("A was already deleted before the crash.")
print("B remains and must be cleaned.")

if file_a.exists():
    file_a.unlink()

if file_b.exists():
    file_b.unlink()

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert not file_b.exists()

print("PASS")


print()
print("10. DURABLE COMPLETION:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

action = state["actions"][0]

complete = complete_execution(
    action,
    result="cleanup-reconciled-success",
)

print("COMPLETE:", complete)

assert complete["status"] == "executed"

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
assert action["retry_count"] == 1

print("PASS")


print()
print("11. FINAL REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert not file_b.exists()

print("PASS")


print()
print("12. AUDIT LIFECYCLE:")

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

observed = [e.get("event") for e in events]

assert "execution-started" in observed
assert "recovery-interrupted" in observed
assert "retry-approved" in observed
assert "execution-completed" in observed

print("PASS")


print()
print("13. AMBIGUOUS-COMPLETION INVARIANTS:")

print("REAL-WORLD SIDE EFFECT OCCURRED BEFORE CRASH")
print("DURABLE COMPLETION WAS NOT WRITTEN")
print("RECOVERY DID NOT CLAIM SUCCESS")
print("RECOVERY PRESERVED ACTUAL WORLD STATE")
print("RECOVERY DID NOT CONSUME RETRY BUDGET")
print("RETRY REQUIRED EXPLICIT AUTHORIZATION")
print("RETRY OBSERVED CURRENT WORLD STATE")
print("ALREADY-COMPLETED SIDE EFFECT WAS NOT RECREATED")
print("REMAINING WORK WAS COMPLETED")
print("FINAL DURABLE STATE MATCHED REAL-WORLD STATE")
print("AUDIT PRESERVED THE AMBIGUOUS-COMPLETION LIFECYCLE")


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
