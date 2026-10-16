import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from judgment.audit import load_audit
from judgment.lifecycle import begin_execution, complete_execution, retry_failed_action
from judgment.execution import execute_action
from judgment.recovery import STATE_PATH, recover_interrupted_actions

print("=== REAL-WORLD RETRY CRASH → RECOVERY → RE-ESCALATION DURABILITY TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_retry_crash_reescalation_sandbox"
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


def mark_execution_stale():
    current_state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    current_state["actions"][0]["execution_started_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    STATE_PATH.write_text(
        json.dumps(current_state, indent=2),
        encoding="utf-8",
    )


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
print("2. FIRST EXECUTION → PARTIAL SIDE EFFECT:")

start = execute_action(ACTION)
print("START:", start)

assert start["status"] == "executing"

file_a.unlink()

assert not file_a.exists()
assert file_b.exists()
assert file_c.exists()

print("A deleted:", not file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())
print("PASS")

print()
print("3. CRASH BEFORE FIRST EXECUTION COMPLETION:")

print("Simulated crash.")

mark_execution_stale()
recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
assert action["retry_count"] == 0

print(
    ACTION,
    "| failed | interrupted-by-restart",
    "| retry_count =", action["retry_count"],
)

print("PASS")

print()
print("4. FIRST EXPLICIT RETRY:")

retry = retry_failed_action(ACTION)

print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
assert retry["escalation_required"] is False

print("PASS")

print()
print("5. RETRY EXECUTION → PARTIAL SIDE EFFECT:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

print("Retry cleans B before crash.")

file_b.unlink()

assert not file_b.exists()
assert file_c.exists()

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

print("PASS")

print()
print("6. CRASH DURING RETRY #1:")

print("Crash occurs before retry #1 can durably complete.")

mark_execution_stale()
recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
    "| escalation =", action["escalation_required"],
)

assert ACTION in recovered
assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"

# Critical invariant:
# recovery must NOT reset or increment the retry budget.
assert action["retry_count"] == 1
assert action["max_retries"] == 2
assert action["escalation_required"] is False

print("Retry budget preserved at 1.")
print("PASS")

print()
print("7. ACTUAL FILESYSTEM STATE AFTER RETRY CRASH:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("Partial retry side effect preserved.")
print("PASS")

print()
print("8. SECOND EXPLICIT RETRY:")

retry = retry_failed_action(ACTION)

print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 2
assert retry["max_retries"] == 2
assert retry["escalation_required"] is False

print("PASS")

print()
print("9. RETRY #2 EXECUTION → FAILURE:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

print("C cannot be cleaned.")
print("Simulating persistent cleanup failure.")

failure = execute_action(
    ACTION,
    result="cleanup-failed-permission-denied",
    complete=True,
    success=False,
)

print("FAILURE:", failure)

assert failure["status"] == "failed"

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

assert action["retry_count"] == 2
assert action["escalation_required"] is False

print("PASS")

print()
print("10. RETRY EXHAUSTION → RE-ESCALATION:")

blocked = retry_failed_action(ACTION)

print(blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["max_retries"] == 2
assert blocked["escalation_required"] is True

print("PASS")

print()
print("11. FINAL REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("C remains because cleanup ultimately failed.")
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

assert action["status"] == "failed"
assert action["retry_count"] == 2
assert action["max_retries"] == 2
assert action["escalation_required"] is True

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

assert "recovery-interrupted" in observed
assert "retry-approved" in observed
assert "retry-blocked" in observed

print("PASS")

print()
print("14. FINAL RETRY-CRASH INVARIANTS:")

print("FIRST EXECUTION CRASH WAS RECOVERED")
print("FIRST RETRY WAS EXPLICITLY AUTHORIZED")
print("RETRY #1 PRODUCED A REAL-WORLD SIDE EFFECT")
print("CRASH DURING RETRY #1 DID NOT RESET RETRY_COUNT")
print("RECOVERY PRESERVED retry_count = 1")
print("SECOND RETRY REQUIRED EXPLICIT AUTHORIZATION")
print("RETRY #2 FAILED")
print("RETRY EXHAUSTION CAUSED RE-ESCALATION")
print("ESCALATION REMAINED DURABLE")
print("NO RETRY WAS MANUFACTURED BY RECOVERY")
print("AUDIT PRESERVED THE COMPLETE MULTI-CYCLE LIFECYCLE")

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
