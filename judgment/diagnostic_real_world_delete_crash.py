import json

from pathlib import Path
from judgment.audit import load_audit
from judgment.recovery import STATE_PATH, recover_interrupted_actions

print("=== REAL-WORLD DELETE → CRASH BEFORE COMPLETION → RECOVERY TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_delete_crash_sandbox"
SANDBOX.mkdir(parents=True, exist_ok=True)

target_file = SANDBOX / "delete_me.tmp"
target_file.write_text("real-world side effect simulation", encoding="utf-8")

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
print("1. REAL-WORLD TARGET:")
print("target:", target_file)
print("exists:", target_file.exists())
assert target_file.exists()
print("PASS")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

action["status"] = "executing"
action["execution_result"] = "cleanup-started"
action["cleanup_target"] = str(target_file)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("2. EXECUTION STARTED:")
print(ACTION, "| executing")
print("PASS")

print()
print("3. ACTUAL REAL-WORLD SIDE EFFECT:")
target_file.unlink()

print("delete operation completed:", not target_file.exists())
assert not target_file.exists()
print("PASS")

print()
print("4. SIMULATED CRASH:")
print("Crash occurs BEFORE durable state is changed to executed.")
print("PASS")

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
)

assert ACTION in recovered
assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"

print("PASS")

print()
print("6. ACTUAL WORLD STATE VERIFICATION:")

print("target exists:", target_file.exists())

assert not target_file.exists()

print("Actual deletion remained true.")
print("Recovery did NOT manufacture a second deletion.")
print("PASS")

print()
print("7. RETRY BUDGET:")

print(
    "retry_count =",
    action["retry_count"],
    "| max_retries =",
    action["max_retries"],
)

assert action["retry_count"] == 0

print("Recovery did not consume a retry slot.")
print("PASS")

print()
print("8. AUDIT:")

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

print("PASS")

print()
print("9. FINAL INVARIANT:")
print("REAL-WORLD SIDE EFFECT OCCURRED BEFORE CRASH")
print("DURABLE STATE DID NOT FALSELY CLAIM SUCCESS")
print("RECOVERY DID NOT MANUFACTURE SUCCESS")
print("ACTUAL DELETION REMAINED CONSISTENT")
print("RECOVERY DID NOT CONSUME RETRY BUDGET")
print("RECOVERY REMAINED AUDITABLE")

if target_file.exists():
    target_file.unlink()

if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass

print()
print("RESULT: PASS")
