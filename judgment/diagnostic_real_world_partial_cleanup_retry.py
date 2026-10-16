import json
from pathlib import Path

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.retry import retry_failed_action
from judgment.execution import execute_action

print("=== REAL-WORLD PARTIAL CLEANUP → CRASH → RECOVERY → RETRY TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_retry_cleanup_sandbox"
SANDBOX.mkdir(parents=True, exist_ok=True)

file_a = SANDBOX / "cleanup_a.tmp"
file_b = SANDBOX / "cleanup_b.tmp"
file_c = SANDBOX / "cleanup_c.tmp"

for f in (file_a, file_b, file_c):
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
print("1. INITIAL REAL-WORLD STATE:")
print("A:", file_a.exists())
print("B:", file_b.exists())
print("C:", file_c.exists())
assert file_a.exists() and file_b.exists() and file_c.exists()
print("PASS")

print()
print("2. CLEANUP EXECUTION START:")

start = execute_action(ACTION)
print("START:", start)
assert start["status"] == "executing"

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

action["cleanup_targets"] = [
    str(file_a),
    str(file_b),
    str(file_c),
]
action["execution_result"] = "partial-cleanup"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print(ACTION, "| executing")
print("PASS")

print()
print("3. PARTIAL REAL-WORLD SIDE EFFECT:")

file_a.unlink()
file_b.unlink()

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("A deleted:", not file_a.exists())
print("B deleted:", not file_b.exists())
print("C remains:", file_c.exists())
print("PASS")

print()
print("4. SIMULATED CRASH:")
print("Crash occurs before durable execution completion.")
print("PASS")

# Simulate an execution that has been stale beyond recovery's five-minute timeout.
from datetime import datetime, timedelta, timezone

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]
action["execution_started_at"] = (
    datetime.now(timezone.utc) - timedelta(minutes=10)
).isoformat()
STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

print()
print("5. FRESH PROCESS RECOVERY:")

recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "|",
    action["status"],
    "|",
    action.get("execution_result"),
    "| retry_count =",
    action["retry_count"],
)

assert ACTION in recovered
assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
assert action["retry_count"] == 0

print("PASS")

print()
print("6. VERIFY ACTUAL FILESYSTEM STATE:")

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())
print("Recovery preserved the partial real-world state.")
print("PASS")

print()
print("7. EXPLICIT RETRY AUTHORIZATION:")

retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
assert retry["escalation_required"] is False

print("PASS")

print()
print("8. RETRY EXECUTION:")

start = execute_action(ACTION)
print("START:", start)
assert start["status"] == "executing"

print("Completing remaining cleanup: C")

if file_c.exists():
    file_c.unlink()

complete = execute_action(
    ACTION,
    result="remaining-cleanup-success",
    complete=True,
)

print("COMPLETE:", complete)
assert complete["status"] == "executed"

print("PASS")

print()
print("9. FINAL REAL-WORLD STATE:")

assert not file_a.exists()
assert not file_b.exists()
assert not file_c.exists()

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())
print("All cleanup targets removed.")
print("PASS")

print()
print("10. FINAL DURABLE STATE:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "| status =",
    action["status"],
    "| result =",
    action.get("execution_result"),
    "| retry_count =",
    action["retry_count"],
    "| escalation =",
    action["escalation_required"],
)

assert action["status"] == "executed"
assert action["execution_result"] == "remaining-cleanup-success"
assert action["retry_count"] == 1
assert action["escalation_required"] is False

print("PASS")

print()
print("11. AUDIT LIFECYCLE:")

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

observed = {e.get("event") for e in events}

assert "execution-started" in observed
assert "recovery-interrupted" in observed
assert "retry-approved" in observed
assert "execution-completed" in observed

print("PASS")

print()
print("12. FINAL REAL-WORLD INVARIANT:")

print("PARTIAL SIDE EFFECT OCCURRED BEFORE CRASH")
print("RECOVERY PRESERVED ACTUAL FILESYSTEM STATE")
print("RECOVERY DID NOT CONSUME RETRY BUDGET")
print("RETRY REQUIRED EXPLICIT AUTHORIZATION")
print("EXACTLY ONE RETRY WAS CONSUMED")
print("REMAINING CLEANUP COMPLETED SUCCESSFULLY")
print("FINAL DURABLE STATE MATCHED REAL-WORLD STATE")
print("RECOVERY AND RETRY REMAINED AUDITABLE")

print()
print("RESULT: PASS")

for f in (file_a, file_b, file_c):
    if f.exists():
        f.unlink()

if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass

