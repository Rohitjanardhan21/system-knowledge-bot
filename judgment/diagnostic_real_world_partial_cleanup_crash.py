import json
from pathlib import Path

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH, recover_interrupted_actions

print("=== REAL-WORLD PARTIAL CLEANUP → CRASH → RECOVERY TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_partial_cleanup_sandbox"
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

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

action["status"] = "executing"
action["execution_result"] = "partial-cleanup"
action["cleanup_targets"] = [
    str(file_a),
    str(file_b),
    str(file_c),
]

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("2. CLEANUP EXECUTION STARTED:")
print(ACTION, "| executing")
print("PASS")

print()
print("3. PARTIAL REAL-WORLD SIDE EFFECT:")

file_a.unlink()
file_b.unlink()

print("A deleted:", not file_a.exists())
print("B deleted:", not file_b.exists())
print("C remains:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("Partial cleanup occurred.")
print("PASS")

print()
print("4. SIMULATED CRASH:")
print("Crash occurs BEFORE durable execution completion.")
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
print("6. ACTUAL FILESYSTEM STATE AFTER RECOVERY:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("Partial real-world state was preserved.")
print("Recovery did NOT manufacture success.")
print("PASS")

print()
print("7. RECOVERY DID NOT PERFORM SIDE EFFECTS:")

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

print("Deleted files remained deleted.")
print("Undeleted file remained undeleted.")
print("PASS")

print()
print("8. RETRY BUDGET:")

print(
    "retry_count =",
    action["retry_count"],
    "| max_retries =",
    action["max_retries"],
)

assert action["retry_count"] == 0

print("Recovery did not consume retry budget.")
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

recovery_events = [
    e for e in events
    if e.get("event") == "recovery-interrupted"
]

assert len(recovery_events) == 1
assert recovery_events[0]["status"] == "failed"
assert recovery_events[0]["result"] == "interrupted-by-restart"

print("PASS")

print()
print("10. FINAL INVARIANT:")

print("PARTIAL REAL-WORLD SIDE EFFECT OCCURRED")
print("CRASH DID NOT PRODUCE FALSE SUCCESS")
print("RECOVERY PRESERVED ACTUAL FILESYSTEM STATE")
print("RECOVERY DID NOT REPEAT OR REVERSE SIDE EFFECTS")
print("RECOVERY DID NOT CONSUME RETRY BUDGET")
print("INTERRUPTION REMAINED AUDITABLE")

if file_a.exists():
    file_a.unlink()

if file_b.exists():
    file_b.unlink()

if file_c.exists():
    file_c.unlink()

if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass

print()
print("RESULT: PASS")
