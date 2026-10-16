import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.retry import begin_execution, retry_failed_action

print("=== REAL-WORLD MULTI-CRASH PARTIAL CLEANUP → RECOVERY → RETRY TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_multi_crash_cleanup_sandbox"
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

# ============================================================
# FIRST EXECUTION
# ============================================================

print()
print("2. FIRST EXECUTION:")

start = begin_execution(ACTION)
print("START:", start)

assert start["status"] == "executing"

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

action["cleanup_targets"] = [
    str(file_a),
    str(file_b),
    str(file_c),
]
action["execution_result"] = "partial-cleanup-cycle-1"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print("PASS")

# ============================================================
# FIRST PARTIAL SIDE EFFECT
# ============================================================

print()
print("3. FIRST PARTIAL REAL-WORLD SIDE EFFECT:")

file_a.unlink()
file_b.unlink()

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("A deleted:", not file_a.exists())
print("B deleted:", not file_b.exists())
print("C remains:", file_c.exists())
print("PASS")

# ============================================================
# FIRST CRASH
# ============================================================

print()
print("4. FIRST CRASH:")

print("Crash occurs before durable completion.")
print("PASS")

mark_execution_stale()

# ============================================================
# FIRST RECOVERY
# ============================================================

print()
print("5. FIRST FRESH-PROCESS RECOVERY:")

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

# ============================================================
# VERIFY FIRST RECOVERY DID NOT ALTER REAL WORLD
# ============================================================

print()
print("6. FIRST RECOVERY WORLD-STATE CHECK:")

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

print("PASS")

# ============================================================
# RETRY #1
# ============================================================

print()
print("7. EXPLICIT RETRY #1:")

retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
assert retry["escalation_required"] is False

print("PASS")

# ============================================================
# SECOND EXECUTION
# ============================================================

print()
print("8. SECOND EXECUTION:")

start = begin_execution(ACTION)
print("START:", start)

assert start["status"] == "executing"

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

action["execution_result"] = "retry-1-partial-cleanup"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print("PASS")

# ============================================================
# SECOND PARTIAL SIDE EFFECT
# ============================================================

print()
print("9. SECOND PARTIAL REAL-WORLD SIDE EFFECT:")

print("C is still present before second cleanup:", file_c.exists())

# Simulate a second attempt making progress,
# but NOT completing the operation.
# We intentionally leave C in place.

assert file_c.exists()

print("C remains:", file_c.exists())
print("PASS")

# ============================================================
# SECOND CRASH
# ============================================================

print()
print("10. SECOND CRASH:")

print("Crash occurs during retry #1 before durable completion.")
print("PASS")

mark_execution_stale()

# ============================================================
# SECOND RECOVERY
# ============================================================

print()
print("11. SECOND FRESH-PROCESS RECOVERY:")

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
assert action["retry_count"] == 1
assert action["escalation_required"] is False

print("PASS")

# ============================================================
# VERIFY SECOND RECOVERY DID NOT RESET RETRY COUNT
# ============================================================

print()
print("12. SECOND RECOVERY RETRY-BUDGET CHECK:")

print(
    "retry_count =", action["retry_count"],
    "| max_retries =", action["max_retries"],
)

assert action["retry_count"] == 1
assert action["max_retries"] == 2

print("Recovery #2 preserved retry_count = 1.")
print("PASS")

# ============================================================
# REAL WORLD STATE AFTER TWO CRASHES
# ============================================================

print()
print("13. REAL-WORLD STATE AFTER TWO CRASHES:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("Actual filesystem state survived both crashes.")
print("PASS")

# ============================================================
# RETRY #2
# ============================================================

print()
print("14. EXPLICIT RETRY #2:")

retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 2
assert retry["escalation_required"] is False

print("PASS")

# ============================================================
# THIRD EXECUTION FAILURE
# ============================================================

print()
print("15. THIRD EXECUTION → FAILURE:")

start = begin_execution(ACTION)
print("START:", start)

assert start["status"] == "executing"

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

action["status"] = "failed"
action["execution_result"] = "final-cleanup-permission-denied"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print("FAILURE:", {
    "status": action["status"],
    "action": action["action"],
    "result": action["execution_result"],
})

assert action["status"] == "failed"
assert action["retry_count"] == 2

print("PASS")

# ============================================================
# RE-ESCALATION
# ============================================================

print()
print("16. RETRY EXHAUSTION → RE-ESCALATION:")

blocked = retry_failed_action(ACTION)
print(blocked)

assert blocked["status"] == "blocked"
assert blocked["retry_count"] == 2
assert blocked["max_retries"] == 2
assert blocked["escalation_required"] is True

print("PASS")

# ============================================================
# FINAL REAL-WORLD STATE
# ============================================================

print()
print("17. FINAL REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("Partial filesystem state remains accurate.")
print("PASS")

# ============================================================
# DURABLE STATE
# ============================================================

print()
print("18. FINAL DURABLE STATE:")

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

# ============================================================
# AUDIT
# ============================================================

print()
print("19. AUDIT LIFECYCLE:")

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

assert observed.count("execution-started") >= 3
assert observed.count("recovery-interrupted") == 2
assert observed.count("retry-approved") == 2
assert "retry-blocked" in observed

print("PASS")

# ============================================================
# FINAL INVARIANT
# ============================================================

print()
print("20. FINAL MULTI-CRASH REAL-WORLD INVARIANT:")

print("FIRST PARTIAL SIDE EFFECT OCCURRED")
print("FIRST CRASH DID NOT PRODUCE FALSE SUCCESS")
print("FIRST RECOVERY PRESERVED REAL-WORLD STATE")
print("FIRST RETRY REQUIRED EXPLICIT AUTHORIZATION")
print("SECOND CRASH DID NOT RESET RETRY COUNT")
print("SECOND RECOVERY PRESERVED RETRY COUNT")
print("RECOVERY DID NOT CONSUME RETRIES")
print("SECOND RETRY REQUIRED EXPLICIT AUTHORIZATION")
print("RETRY EXHAUSTION RE-ESCALATED THE ACTION")
print("ESCALATION REMAINED DURABLE")
print("NO AUTHORIZATION WAS MANUFACTURED")
print("AUDIT PRESERVED MULTI-CRASH LIFECYCLE")

# Cleanup
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
