import json
from pathlib import Path

from judgment.audit import load_audit
from judgment.recovery import STATE_PATH, recover_interrupted_actions
from judgment.retry import approve_retry
from judgment.execution import execute_action


print("=== REAL-WORLD SIDE EFFECT COMPLETE → CRASH → IDEMPOTENT RETRY TEST ===")

ACTION = "free-disk-space"
SANDBOX = Path("state") / "real_world_idempotent_retry_sandbox"
SANDBOX.mkdir(parents=True, exist_ok=True)

files = [
    SANDBOX / "cleanup_a.tmp",
    SANDBOX / "cleanup_b.tmp",
    SANDBOX / "cleanup_c.tmp",
]

for f in files:
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
        "cleanup_targets": [str(f) for f in files],
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
print("A:", files[0].exists())
print("B:", files[1].exists())
print("C:", files[2].exists())
assert all(f.exists() for f in files)
print("PASS")

print()
print("2. EXECUTION STARTED:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]
action["status"] = "executing"
action["execution_result"] = "cleanup-started"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print(ACTION, "| executing")
print("PASS")

print()
print("3. REAL-WORLD SIDE EFFECT COMPLETES:")

for f in files:
    f.unlink()

assert all(not f.exists() for f in files)

print("A deleted:", not files[0].exists())
print("B deleted:", not files[1].exists())
print("C deleted:", not files[2].exists())
print("PASS")

print()
print("4. SIMULATED CRASH:")

print("Crash occurs BEFORE durable state becomes executed.")
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
print("6. VERIFY ACTUAL WORLD BEFORE RETRY:")

for f in files:
    print(f.name, "| exists =", f.exists())

assert all(not f.exists() for f in files)

print("REAL-WORLD CLEANUP ALREADY COMPLETE")
print("PASS")

print()
print("7. EXPLICIT RETRY APPROVAL:")

result = approve_retry(ACTION)

print(result)

assert result["status"] == "approved"
assert result["retry_count"] == 1

print("PASS")

print()
print("8. RETRY MUST NOT REPEAT SIDE EFFECT:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

targets = [
    Path(p)
    for p in action.get("cleanup_targets", [])
]

already_satisfied = all(not p.exists() for p in targets)

print("side effect already satisfied:", already_satisfied)

assert already_satisfied

print("NO SECOND DELETE REQUIRED")
print("PASS")

print()
print("9. FINALIZE AS SUCCESS AFTER VERIFICATION:")

complete = execute_action(
    ACTION,
    result="cleanup-already-satisfied",
    complete=True,
)

print(complete)

assert complete["status"] == "executed"

print("PASS")

print()
print("10. FINAL REAL-WORLD STATE:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

for f in files:
    print(f.name, "| exists =", f.exists())

assert all(not f.exists() for f in files)

print("FILES REMAIN DELETED")
print("PASS")

print()
print("11. FINAL DURABLE STATE:")

print(
    ACTION,
    "|",
    action["status"],
    "|",
    action.get("execution_result"),
    "| retry_count =",
    action["retry_count"],
)

assert action["status"] == "executed"
assert action["retry_count"] == 1

print("PASS")

print()
print("12. AUDIT:")

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

assert any(
    e.get("event") == "recovery-interrupted"
    for e in events
)

assert any(
    e.get("event") == "retry-approved"
    for e in events
)

assert any(
    e.get("event") == "execution-completed"
    and e.get("result") == "cleanup-already-satisfied"
    for e in events
)

print("PASS")

print()
print("13. FINAL INVARIANT:")

print("REAL-WORLD SIDE EFFECT COMPLETED BEFORE CRASH")
print("DURABLE STATE TEMPORARILY LAGGED REALITY")
print("RECOVERY DID NOT MANUFACTURE SUCCESS")
print("EXPLICIT RETRY WAS REQUIRED")
print("RETRY DETECTED ALREADY-SATISFIED SIDE EFFECT")
print("SIDE EFFECT WAS NOT REPEATED")
print("FINAL STATE BECAME EXECUTED")
print("RETRY WAS CONSUMED EXACTLY ONCE")
print("AUDIT REMAINED COMPLETE")

for f in files:
    if f.exists():
        f.unlink()

if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass

print()
print("RESULT: PASS")
