import json
from pathlib import Path

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.retry import approve_retry
from judgment.execution import execute_action

print("=== REAL-WORLD PARTIAL CLEANUP → CRASH → RECOVERY → RETRY TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_partial_retry_sandbox"
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

print()
print("1. INITIAL REAL-WORLD STATE:")
print("A:", file_a.exists(), "| B:", file_b.exists(), "| C:", file_c.exists())
assert file_a.exists() and file_b.exists() and file_c.exists()
print("PASS")

# Begin actual execution.
state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

action["status"] = "executing"
action["execution_result"] = "partial-cleanup"
action["cleanup_targets"] = [str(file_a), str(file_b), str(file_c)]

STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

print()
print("2. CLEANUP EXECUTION STARTED:")
print(ACTION, "| executing")
print("PASS")

# Real-world partial side effect.
file_a.unlink()
file_b.unlink()

print()
print("3. PARTIAL REAL-WORLD SIDE EFFECT:")
print("A deleted:", not file_a.exists())
print("B deleted:", not file_b.exists())
print("C remains:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("PASS")

print()
print("4. SIMULATED CRASH:")
print("Crash occurs before durable execution completion.")
print("PASS")

# Fresh-process recovery.
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

# Verify actual world was not changed by recovery.
print()
print("6. POST-RECOVERY REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("Recovery preserved partial filesystem state.")
print("PASS")

# Explicitly approve retry.
print()
print("7. EXPLICIT RETRY APPROVAL:")

retry = approve_retry(ACTION)

print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
assert retry["escalation_required"] is False

print("PASS")

# Re-authorized execution.
print()
print("8. RE-AUTHORIZED EXECUTION:")

start = execute_action(ACTION)

print("START:", start)

assert start["status"] == "executing"

# Idempotent cleanup:
# already-deleted A/B are left alone;
# only remaining C is removed.
if file_a.exists():
    file_a.unlink()

if file_b.exists():
    file_b.unlink()

if file_c.exists():
    file_c.unlink()

complete = execute_action(
    ACTION,
    result="partial-cleanup-recovered-success",
    complete=True,
)

print("COMPLETE:", complete)

assert complete["status"] == "executed"

print("PASS")

# Final durable state.
print()
print("9. FINAL DURABLE STATE:")

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
    "| escalation =",
    action["escalation_required"],
)

assert action["status"] == "executed"
assert action["execution_result"] == "partial-cleanup-recovered-success"
assert action["retry_count"] == 1
assert action["escalation_required"] is False

print("PASS")

# Verify actual filesystem.
print()
print("10. FINAL REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert not file_c.exists()

print("All cleanup targets are now deleted.")
print("PASS")

# Audit verification.
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

assert "recovery-interrupted" in observed
assert "retry-approved" in observed
assert "execution-started" in observed
assert "execution-completed" in observed

print("PASS")

# Cleanup sandbox.
for f in (file_a, file_b, file_c):
    if f.exists():
        f.unlink()

if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass

print()
print("12. FINAL REAL-WORLD INVARIANT:")
print("PARTIAL SIDE EFFECT OCCURRED BEFORE CRASH")
print("RECOVERY DID NOT CLAIM FALSE SUCCESS")
print("RECOVERY PRESERVED ACTUAL FILESYSTEM STATE")
print("EXPLICIT RETRY RESTORED EXECUTION AUTHORITY")
print("ALREADY-DELETED FILES WERE NOT RECREATED OR DOUBLE-DELETED")
print("REMAINING WORK WAS COMPLETED")
print("EXACTLY ONE RETRY WAS CONSUMED")
print("FINAL DURABLE STATE MATCHED REAL-WORLD STATE")
print("FULL LIFECYCLE REMAINED AUDITABLE")

print()
print("RESULT: PASS")
