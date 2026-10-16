import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from judgment.audit import load_audit
from judgment.lifecycle import begin_execution, complete_execution, retry_failed_action
from judgment.recovery import STATE_PATH, recover_interrupted_actions

print("=== REAL-WORLD PARTIAL CLEANUP → CRASH → RETRY FAILURE → RE-ESCALATION TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_reescalation_sandbox"
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
STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

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
assert file_a.exists() and file_b.exists() and file_c.exists()
print("PASS")

print()
print("2. FIRST EXECUTION:")
start = begin_execution(ACTION)
print("START:", start)
assert start["status"] == "executing"

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]
action["cleanup_targets"] = [str(file_a), str(file_b), str(file_c)]
action["execution_result"] = "partial-cleanup"

STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

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
print("Crash occurs before durable completion.")
print("PASS")

mark_execution_stale()

print()
print("5. FRESH PROCESS RECOVERY:")
recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "|", action["status"],
    "|", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
)

assert ACTION in recovered
assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
assert action["retry_count"] == 0
print("PASS")

print()
print("6. VERIFY PARTIAL REAL-WORLD STATE:")
assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())
print("PASS")

print()
print("7. FIRST EXPLICIT RETRY:")
retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
assert retry["escalation_required"] is False
print("PASS")

print()
print("8. RETRY EXECUTION:")
start = begin_execution(ACTION)
print("START:", start)
assert start["status"] == "executing"

print("Simulating retry failure: C cannot be cleaned.")

complete = complete_execution(
    ACTION,
    result="cleanup-failed-permission-denied",
    success=False,
)

print("FAILURE:", complete)

assert complete["status"] == "failed"

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

assert action["retry_count"] == 1
assert action["escalation_required"] is False

print(
    ACTION,
    "| status =", action["status"],
    "| retry_count =", action["retry_count"],
    "| escalation =", action["escalation_required"],
)
print("PASS")

print()
print("9. SECOND EXPLICIT RETRY:")
retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 2
assert retry["escalation_required"] is False
print("PASS")

print()
print("10. SECOND RETRY EXECUTION → FAILURE:")
start = begin_execution(ACTION)
print("START:", start)
assert start["status"] == "executing"

complete = complete_execution(
    ACTION,
    result="cleanup-failed-permission-denied-again",
    success=False,
)

print("FAILURE:", complete)
assert complete["status"] == "failed"

print("PASS")

print()
print("11. RETRY EXHAUSTION → RE-ESCALATION:")
blocked = retry_failed_action(ACTION)
print(blocked)

assert blocked["status"] == "blocked"
assert blocked["escalation_required"] is True
assert blocked["retry_count"] == 2

print("PASS")

print()
print("12. ACTUAL REAL-WORLD STATE:")
print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("Partial filesystem state remained intact.")
print("PASS")

print()
print("13. DURABLE STATE:")
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
print("14. AUDIT LIFECYCLE:")
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
assert "retry-blocked" in observed

print("PASS")

print()
print("15. FINAL REAL-WORLD RE-ESCALATION INVARIANT:")
print("PARTIAL SIDE EFFECT OCCURRED BEFORE CRASH")
print("RECOVERY PRESERVED ACTUAL FILESYSTEM STATE")
print("RECOVERY DID NOT CONSUME RETRY BUDGET")
print("FIRST RETRY REQUIRED EXPLICIT AUTHORIZATION")
print("RETRY FAILURE DID NOT DOUBLE-CONSUME RETRIES")
print("SECOND RETRY REQUIRED EXPLICIT AUTHORIZATION")
print("RETRY EXHAUSTION RE-ESCALATED THE ACTION")
print("ESCALATION REMAINED DURABLE")
print("NO AUTHORIZATION WAS MANUFACTURED")
print("AUDIT PRESERVED THE COMPLETE LIFECYCLE")

for f in (file_a, file_b, file_c):
    if f.exists():
        f.unlink()

if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass

print()
print("RESULT: PASS")
