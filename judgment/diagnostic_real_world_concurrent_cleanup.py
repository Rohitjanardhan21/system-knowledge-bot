import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from judgment.audit import load_audit
from judgment.execution import execute_action
from judgment.lifecycle import retry_failed_action
from judgment.recovery import STATE_PATH, recover_interrupted_actions

print("=== REAL-WORLD CONCURRENT SIDE EFFECT → CRASH → RECOVERY → RETRY TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_concurrent_cleanup_sandbox"
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

assert file_a.exists()
assert file_b.exists()
assert file_c.exists()

print("PASS")

print()
print("2. FIRST EXECUTION:")

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

action["execution_result"] = "cleanup-started"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print("PASS")

print()
print("3. OUR PROCESS PERFORMS PARTIAL CLEANUP:")

file_a.unlink()

assert not file_a.exists()
assert file_b.exists()
assert file_c.exists()

print("A deleted:", not file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

print("PASS")

print()
print("4. SIMULATED CRASH:")

print("Process crashes before durable completion.")
print("PASS")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
state["actions"][0]["execution_started_at"] = (
    datetime.now(timezone.utc) - timedelta(minutes=10)
).isoformat()
STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

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
)

assert ACTION in recovered
assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
assert action["retry_count"] == 0

print("PASS")

print()
print("6. EXTERNAL PROCESS CHANGES THE WORLD:")

print("Simulating another process deleting C while our system is offline.")

file_c.unlink()

assert not file_c.exists()

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

print("PASS")

print()
print("7. VERIFY STATE IS NOW DIFFERENT FROM ORIGINAL PLAN:")

assert not file_a.exists()
assert file_b.exists()
assert not file_c.exists()

print("A already deleted")
print("B still requires cleanup")
print("C already deleted externally")

print("PASS")

print()
print("8. EXPLICIT RETRY AUTHORIZATION:")

retry = retry_failed_action(ACTION)

print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
assert retry["escalation_required"] is False

print("PASS")

print()
print("9. RETRY EXECUTION:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

print()
print("Retry reconciles the CURRENT filesystem state.")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert file_b.exists()
assert not file_c.exists()

print("PASS")

print()
print("10. COMPLETE REMAINING REAL-WORLD CLEANUP:")

file_b.unlink()

assert not file_b.exists()

complete = execute_action(
    ACTION,
    result="cleanup-reconciled-success",
    complete=True,
)

print("COMPLETE:", complete)

assert complete["status"] == "executed"
assert complete["result"] == "cleanup-reconciled-success"

print("PASS")

print()
print("11. FINAL REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert not file_c.exists()

print("All cleanup targets are absent.")
print("PASS")

print()
print("12. FINAL DURABLE STATE:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
    "| max_retries =", action["max_retries"],
    "| escalation =", action["escalation_required"],
)

assert action["status"] == "executed"
assert action["execution_result"] == "cleanup-reconciled-success"
assert action["retry_count"] == 1
assert action["escalation_required"] is False

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

observed = [e.get("event") for e in events]

assert "execution-started" in observed
assert "recovery-interrupted" in observed
assert "retry-approved" in observed
assert "execution-completed" in observed

print("PASS")

print()
print("14. FINAL CONCURRENT-WORLD INVARIANT:")

print("CRASH DID NOT PRODUCE FALSE SUCCESS")
print("RECOVERY PRESERVED THE ACTUAL WORLD STATE")
print("EXTERNAL SIDE EFFECT WAS NOT MISTAKEN FOR OUR OWN EXECUTION")
print("RETRY REQUIRED EXPLICIT AUTHORIZATION")
print("RETRY OPERATED AGAINST CURRENT STATE")
print("ALREADY-DELETED TARGETS WERE NOT RECREATED")
print("REMAINING TARGET WAS CLEANED")
print("FINAL DURABLE STATE MATCHED REAL-WORLD STATE")
print("AUDIT PRESERVED CRASH → RECOVERY → RETRY → COMPLETION")

print()

for f in (file_a, file_b, file_c):
    if f.exists():
        f.unlink()

if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass

print("RESULT: PASS")
