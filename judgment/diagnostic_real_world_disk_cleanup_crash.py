import json
import os
from pathlib import Path

from judgment.audit import load_audit
from judgment.execution import STATE_PATH
from judgment.recovery import recover_interrupted_actions


print("=== REAL-WORLD DISK CLEANUP → CRASH → RECOVERY TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_disk_cleanup_sandbox"
SANDBOX.mkdir(parents=True, exist_ok=True)

test_file = SANDBOX / "cleanup_target.tmp"
test_file.write_text("simulated temporary data", encoding="utf-8")

# Establish an authorized execution state.
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
print("1. REAL-WORLD SANDBOX:")
print("temporary file:", test_file)
print("exists:", test_file.exists())
print("PASS")

# Simulate the remediation actually beginning.
state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
target = state["actions"][0]
target["status"] = "executing"
target["execution_result"] = "cleanup-started"
target["cleanup_target"] = str(test_file)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("2. CLEANUP STARTED:")
print(ACTION, "| executing")
print("cleanup target exists:", test_file.exists())
print("PASS")

# Simulate a process crash BEFORE cleanup completion.
print()
print("3. SIMULATED PROCESS CRASH:")
print("Crash occurs before cleanup completion.")
print("PASS")

# Fresh-process recovery.
print()
print("4. FRESH PROCESS RECOVERY:")
recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
target = state["actions"][0]

print(
    ACTION,
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)
assert ACTION in recovered
assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"
print("PASS")

# Verify that recovery did NOT falsely claim cleanup succeeded.
print()
print("5. ACTUAL SANDBOX VERIFICATION:")
print("cleanup target still exists:", test_file.exists())
assert test_file.exists()
print("Recovery did not manufacture cleanup success.")
print("PASS")

# Verify retry budget was not consumed by recovery.
print()
print("6. RETRY BUDGET:")
print(
    "retry_count =",
    target.get("retry_count"),
    "| max_retries =",
    target.get("max_retries"),
)
assert target.get("retry_count") == 0
print("Recovery did not consume a retry slot.")
print("PASS")

# Verify audit.
print()
print("7. AUDIT:")
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

recovery_events = [
    e for e in events
    if e.get("event") == "recovery-interrupted"
]

assert len(recovery_events) == 1
assert recovery_events[0]["status"] == "failed"
assert recovery_events[0]["result"] == "interrupted-by-restart"
print("PASS")

# Cleanup sandbox.
if test_file.exists():
    test_file.unlink()

if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass

print()
print("8. FINAL INVARIANT:")
print("CRASH DID NOT PRODUCE FALSE SUCCESS")
print("RECOVERY CONVERTED INTERRUPTED EXECUTION TO FAILED")
print("ACTUAL SANDBOX STATE REMAINED CONSISTENT")
print("RETRY BUDGET WAS NOT CONSUMED BY RECOVERY")
print("RECOVERY REMAINED AUDITABLE")
print()
print("RESULT: PASS")
